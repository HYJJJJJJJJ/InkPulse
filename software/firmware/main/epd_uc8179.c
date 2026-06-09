// E075A42 / UC8179 7.5" 800x480 BWR 驱动
// 极性约定(bring-up Task5 验证): 发给 0x10(B/W) 字节 1=白 0=黑; 发给 0x13(RED) 字节 1=红 0=不红
// 清屏=白: 0x10<-0xFF, 0x13<-0x00
#include "epd_uc8179.h"
#include "pins.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "epd";
static spi_device_handle_t s_spi;

void epd_hal_init(void)
{
    gpio_config_t out = {
        .pin_bit_mask = (1ULL << EPD_PIN_DC) | (1ULL << EPD_PIN_RST),
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&out);

    gpio_config_t in = {
        .pin_bit_mask = (1ULL << EPD_PIN_BUSY),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    gpio_config(&in);

    spi_bus_config_t bus = {
        .mosi_io_num = EPD_PIN_MOSI,
        .miso_io_num = -1,
        .sclk_io_num = EPD_PIN_SCLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 4096,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));

    spi_device_interface_config_t dev = {
        .clock_speed_hz = 10 * 1000 * 1000, // 10MHz
        .mode = 0,                          // CPOL=0 CPHA=0
        .spics_io_num = EPD_PIN_CS,
        .queue_size = 4,
    };
    ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &dev, &s_spi));
    ESP_LOGI(TAG, "HAL init done");
}

static void spi_tx(const uint8_t *data, size_t len)
{
    spi_transaction_t t = { .length = len * 8, .tx_buffer = data };
    ESP_ERROR_CHECK(spi_device_polling_transmit(s_spi, &t));
}

void epd_send_cmd(uint8_t cmd)
{
    gpio_set_level(EPD_PIN_DC, 0);
    spi_tx(&cmd, 1);
}

void epd_send_data(uint8_t data)
{
    gpio_set_level(EPD_PIN_DC, 1);
    spi_tx(&data, 1);
}

void epd_send_data_buf(const uint8_t *buf, size_t len)
{
    gpio_set_level(EPD_PIN_DC, 1);
    size_t off = 0;
    while (off < len) {
        size_t chunk = (len - off > 4096) ? 4096 : (len - off);
        spi_tx(buf + off, chunk);
        off += chunk;
    }
}

void epd_reset(void)
{
    gpio_set_level(EPD_PIN_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(EPD_PIN_RST, 0);
    vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level(EPD_PIN_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(20));
}

void epd_wait_busy(void)
{
    // BUSY_N: 低=忙, 高=空闲。等到高电平。
    ESP_LOGI(TAG, "wait busy...");
    int waited = 0;
    while (gpio_get_level(EPD_PIN_BUSY) == 0) {
        vTaskDelay(pdMS_TO_TICKS(50));
        waited += 50;
        if (waited % 2000 == 0) {
            ESP_LOGI(TAG, "  still busy %dms", waited);
        }
        if (waited > 40000) {
            ESP_LOGW(TAG, "  busy timeout(40s) — 检查复位/电源/引脚");
            break;
        }
    }
    ESP_LOGI(TAG, "busy released after %dms", waited);
}

void epd_init(void)
{
    epd_reset();

    // PWR: 电源设置(内部DC/DC, VGH/VGL=±20V, VDH/VDL=±15V) — UC8179 7.5BWR 通行值
    epd_send_cmd(0x01);
    epd_send_data(0x07); epd_send_data(0x07);
    epd_send_data(0x3f); epd_send_data(0x3f);

    epd_send_cmd(0x04);   // PON 上电
    vTaskDelay(pdMS_TO_TICKS(100));
    epd_wait_busy();

    epd_send_cmd(0x00); epd_send_data(0x0F);   // PSR: BWR + OTP LUT, booster on

    epd_send_cmd(0x61);                          // TRES 分辨率 800x480
    epd_send_data(0x03); epd_send_data(0x20);
    epd_send_data(0x01); epd_send_data(0xE0);

    epd_send_cmd(0x15); epd_send_data(0x00);     // DUSPI 单SPI

    epd_send_cmd(0x50); epd_send_data(0x11); epd_send_data(0x07); // CDI VCOM/数据间隔

    epd_send_cmd(0x60); epd_send_data(0x22);     // TCON

    ESP_LOGI(TAG, "epd_init done");
}

void epd_fill_plane(uint8_t cmd, uint8_t value)
{
    static uint8_t row[EPD_ROW_BYTES];
    memset(row, value, sizeof(row));
    epd_send_cmd(cmd);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        epd_send_data_buf(row, sizeof(row));
    }
}

void epd_refresh(void)
{
    epd_send_cmd(0x12);   // DRF
    vTaskDelay(pdMS_TO_TICKS(100));
    epd_wait_busy();
}

void epd_clear(void)
{
    epd_fill_plane(0x10, 0xFF);  // B/W plane = 全白
    epd_fill_plane(0x13, 0x00);  // RED plane = 无红
    epd_refresh();
}

void epd_sleep(void)
{
    epd_send_cmd(0x02);   // POF
    epd_wait_busy();
    epd_send_cmd(0x07); epd_send_data(0xA5);  // DSLP
}

// ---- 测试图案 ----
void epd_show_solid(uint8_t bw_val, uint8_t red_val)
{
    epd_fill_plane(0x10, bw_val);
    epd_fill_plane(0x13, red_val);
    epd_refresh();
}

void epd_show_split(void)
{
    static uint8_t row[EPD_ROW_BYTES];
    // B/W plane: 上半黑(0x00) 下半白(0xFF)
    epd_send_cmd(0x10);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        memset(row, (y < EPD_HEIGHT / 2) ? 0x00 : 0xFF, sizeof(row));
        epd_send_data_buf(row, sizeof(row));
    }
    // RED plane: 上半不红(0x00) 下半红(0xFF)
    epd_send_cmd(0x13);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        memset(row, (y < EPD_HEIGHT / 2) ? 0x00 : 0xFF, sizeof(row));
        epd_send_data_buf(row, sizeof(row));
    }
    epd_refresh();
}

void epd_show_checker(void)
{
    static uint8_t row[EPD_ROW_BYTES];
    epd_send_cmd(0x10);  // 64px 方格: 行带与列带异或
    for (int y = 0; y < EPD_HEIGHT; y++) {
        uint8_t band = (y / 64) & 1;
        for (int xb = 0; xb < EPD_ROW_BYTES; xb++) {
            uint8_t col = ((xb * 8) / 64) & 1;
            row[xb] = (band ^ col) ? 0x00 : 0xFF;  // 黑/白交替
        }
        epd_send_data_buf(row, sizeof(row));
    }
    epd_fill_plane(0x13, 0x00);  // 无红
    epd_refresh();
}
