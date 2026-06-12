// ip_hal/spi_bus.c — SPI 总线 HAL (EPD UC8179)
// 从 main/epd_uc8179.c 抽取硬件操作部分封装
#include "ip_hal/spi_bus.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "hal_spi";

// 保存运行时引脚号(由 hal_spi_init 参数注入)
static int s_dc;
static int s_rst;
static int s_busy;
static spi_device_handle_t s_spi;

esp_err_t hal_spi_init(int mosi, int sclk, int cs, int dc, int rst, int busy)
{
    s_dc   = dc;
    s_rst  = rst;
    s_busy = busy;

    // DC / RST 配置为输出
    gpio_config_t out = {
        .pin_bit_mask = (1ULL << dc) | (1ULL << rst),
        .mode         = GPIO_MODE_OUTPUT,
    };
    esp_err_t err = gpio_config(&out);
    if (err != ESP_OK) return err;

    // BUSY 配置为输入上拉
    gpio_config_t in = {
        .pin_bit_mask = (1ULL << busy),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
    };
    err = gpio_config(&in);
    if (err != ESP_OK) return err;

    // SPI 总线初始化 (SPI2_HOST, max_transfer_sz 4096)
    spi_bus_config_t bus = {
        .mosi_io_num     = mosi,
        .miso_io_num     = -1,
        .sclk_io_num     = sclk,
        .quadwp_io_num   = -1,
        .quadhd_io_num   = -1,
        .max_transfer_sz = 4096,
    };
    err = spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) return err;

    // 添加设备: 10MHz, mode0, CS 引脚, queue_size 4
    spi_device_interface_config_t dev = {
        .clock_speed_hz = 10 * 1000 * 1000,
        .mode           = 0,
        .spics_io_num   = cs,
        .queue_size     = 4,
    };
    err = spi_bus_add_device(SPI2_HOST, &dev, &s_spi);
    if (err != ESP_OK) return err;

    ESP_LOGI(TAG, "hal_spi_init done (mosi=%d sclk=%d cs=%d dc=%d rst=%d busy=%d)",
             mosi, sclk, cs, dc, rst, busy);
    return ESP_OK;
}

// 内部: 裸 SPI 传输
static void spi_tx(const uint8_t *data, size_t len)
{
    spi_transaction_t t = { .length = len * 8, .tx_buffer = data };
    ESP_ERROR_CHECK(spi_device_polling_transmit(s_spi, &t));
}

void hal_spi_cmd(uint8_t cmd)
{
    gpio_set_level(s_dc, 0);
    spi_tx(&cmd, 1);
}

void hal_spi_data(uint8_t data)
{
    gpio_set_level(s_dc, 1);
    spi_tx(&data, 1);
}

void hal_spi_data_buf(const uint8_t *buf, size_t len)
{
    gpio_set_level(s_dc, 1);
    size_t off = 0;
    while (off < len) {
        size_t chunk = (len - off > 4096) ? 4096 : (len - off);
        spi_tx(buf + off, chunk);
        off += chunk;
    }
}

void hal_spi_reset(void)
{
    gpio_set_level(s_rst, 1);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(s_rst, 0);
    vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level(s_rst, 1);
    vTaskDelay(pdMS_TO_TICKS(20));
}

int hal_spi_busy_level(void)
{
    return gpio_get_level(s_busy);
}
