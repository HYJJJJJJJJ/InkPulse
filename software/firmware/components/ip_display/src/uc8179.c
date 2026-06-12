// UC8179 7.5" 800x480 BWR 驱动实现
// 极性约定(bring-up Task5 验证): 发给 0x10(B/W) 字节 1=白 0=黑; 发给 0x13(RED) 字节 1=红 0=不红
// Hub frame 约定: black bit=1->黑, red bit=1->红
// 因此: 0x10 plane 发 ~black(取反), 0x13 plane 直发 red(EPD_RED_INVERT=0)

#include "ip_display/display.h"
#include "uc8179_internal.h"
#include "ip_hal/spi_bus.h"
#include "ip_hal/board_pins.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"
#include <string.h>

static const char *TAG = "uc8179";

// ---- 内部: busy 等待 ----
static void wait_busy(void)
{
    // BUSY_N: 低=忙, 高=空闲。等到高电平。
    ESP_LOGI(TAG, "wait busy...");
    int waited = 0;
    while (hal_spi_busy_level() == 0) {
        vTaskDelay(pdMS_TO_TICKS(50));
        waited += 50;
        if (waited % 2000 == 0) {
            ESP_LOGI(TAG, "  still busy %dms", waited);
        }
        if (waited > 35000) {
            ESP_LOGW(TAG, "  busy 35s 超时");
            break;
        }
    }
    ESP_LOGI(TAG, "busy released after %dms", waited);
}

// ---- 内部: UC8179 上电/寄存器初始化序列 ----
static void uc8179_panel_init(void)
{
    // PWR: 内部 DC/DC, VCOM_SLEW=1, VGH/VGL=±20V, VDH/VDL=±14V, VDHR=3.0V
    hal_spi_cmd(0x01);
    hal_spi_data(0x07); hal_spi_data(0x17);
    hal_spi_data(0x3a); hal_spi_data(0x3a); hal_spi_data(0x03);

    // BTST: 升压软启动(规格书默认)
    hal_spi_cmd(0x06);
    hal_spi_data(0x17); hal_spi_data(0x17);
    hal_spi_data(0x17); hal_spi_data(0x17);

    hal_spi_cmd(0x04);   // PON 上电
    // 注: 本板 PON 后 BUSY 不回高(实测), 故不等 BUSY, 固定延时让升压 ramp;
    // DRF 刷新处仍正常等 BUSY
    vTaskDelay(pdMS_TO_TICKS(800));

    hal_spi_cmd(0x00); hal_spi_data(0x0F);   // PSR: BWR + OTP LUT, booster on

    hal_spi_cmd(0x61);                          // TRES 分辨率 800x480
    hal_spi_data(0x03); hal_spi_data(0x20);
    hal_spi_data(0x01); hal_spi_data(0xE0);

    hal_spi_cmd(0x15); hal_spi_data(0x00);     // DUSPI 单SPI

    hal_spi_cmd(0x50); hal_spi_data(0x11); hal_spi_data(0x07); // CDI VCOM/数据间隔

    hal_spi_cmd(0x60); hal_spi_data(0x22);     // TCON

    ESP_LOGI(TAG, "panel init done");
}

// ---- display_if_t 实现 ----

static esp_err_t disp_init(void)
{
    esp_err_t ret = hal_spi_init(
        EPD_PIN_MOSI, EPD_PIN_SCLK, EPD_PIN_CS,
        EPD_PIN_DC,   EPD_PIN_RST,  EPD_PIN_BUSY);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "hal_spi_init failed: %s", esp_err_to_name(ret));
        return ret;
    }
    hal_spi_reset();
    uc8179_panel_init();
    ESP_LOGI(TAG, "disp_init done");
    return ESP_OK;
}

static void disp_get_caps(display_caps_t *out)
{
    out->width       = 800;
    out->height      = 480;
    out->color_model = DISP_BWR;
    out->frame_format = "bwr-dualplane";
    out->frame_bytes  = 96000;   // 48000 black + 48000 red
}

// 内部辅助: 填满一个 plane(供 selftest 调用)
void uc8179_fill_plane(uint8_t cmd, uint8_t value)
{
    static uint8_t row[EPD_ROW_BYTES];
    memset(row, value, sizeof(row));
    hal_spi_cmd(cmd);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        hal_spi_data_buf(row, sizeof(row));
    }
}

// 内部辅助: DRF + 等忙(供 selftest 调用)
void uc8179_refresh(void)
{
    hal_spi_cmd(0x12);   // DRF
    vTaskDelay(pdMS_TO_TICKS(100));
    wait_busy();
}

static esp_err_t disp_show(const uint8_t *frame, size_t len)
{
    if (len < 96000) {
        ESP_LOGE(TAG, "frame too short: %u < 96000", (unsigned)len);
        return ESP_ERR_INVALID_ARG;
    }

    const uint8_t *black = frame;            // 前 48000 字节
    const uint8_t *red   = frame + 48000;    // 后 48000 字节

    static uint8_t tmp[EPD_ROW_BYTES];

    // 0x10(B/W): 1=白 0=黑; Hub black(bit=1->黑) => 发 ~black(取反)
    hal_spi_cmd(0x10);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        const uint8_t *src = black + y * EPD_ROW_BYTES;
        for (int i = 0; i < EPD_ROW_BYTES; i++) tmp[i] = (uint8_t)~src[i];
        hal_spi_data_buf(tmp, EPD_ROW_BYTES);
    }

    // 0x13(RED): 按 EPD_RED_INVERT(bring-up 结论: 1=红 => 直发, EPD_RED_INVERT=0)
    hal_spi_cmd(0x13);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        const uint8_t *src = red + y * EPD_ROW_BYTES;
#if EPD_RED_INVERT
        for (int i = 0; i < EPD_ROW_BYTES; i++) tmp[i] = (uint8_t)~src[i];
        hal_spi_data_buf(tmp, EPD_ROW_BYTES);
#else
        hal_spi_data_buf(src, EPD_ROW_BYTES);
#endif
    }

    return ESP_OK;
}

static void disp_refresh(void)
{
    uc8179_refresh();
}

static void disp_clear(void)
{
    uc8179_fill_plane(0x10, 0xFF);  // B/W plane = 全白
    uc8179_fill_plane(0x13, 0x00);  // RED plane = 无红
    uc8179_refresh();
}

static void disp_sleep(void)
{
    hal_spi_cmd(0x02);   // POF
    wait_busy();
    hal_spi_cmd(0x07); hal_spi_data(0xA5);  // DSLP
}

extern void uc8179_selftest_run(void);   // 在 uc8179_selftest.c

static const display_if_t s_if = {
    .init     = disp_init,
    .get_caps = disp_get_caps,
    .show     = disp_show,
    .refresh  = disp_refresh,
    .clear    = disp_clear,
    .sleep    = disp_sleep,
    .selftest = uc8179_selftest_run,
};

const display_if_t *uc8179_driver(void)
{
    return &s_if;
}
