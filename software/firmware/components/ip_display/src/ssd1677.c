// SSD1677 4.2" 480x800 BW 驱动实现
// caps 报逻辑竖屏 480x800; hub 渲染 480x800 -> 旋转90 -> 800x480 单plane(bit=1=黑) 发来。
// 控制器 RAM: X=源(800), Y=栅(480), 0x24 写 48000B。
// 极性: 0x24 约定 1=白0=黑, 与 hub(1=黑) 相反, 默认 SSD_BW_INVERT=1 取反。真机校准。
#include "ip_display/display.h"
#include "ssd1677_internal.h"
#include "ip_hal/spi_bus.h"
#include "ip_hal/board_pins.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"
#include <string.h>

static const char *TAG = "ssd1677";

static const uint8_t *s_last_frame;   // disp_show 收到的帧指针(指向 main 的 s_framebuf, 长驻)

static void wait_busy(void)
{
    // SSD1677 BUSY: 高=忙(规格书 5-4)。等到低电平。
    int waited = 0;
    while (hal_spi_busy_level() == 1) {
        vTaskDelay(pdMS_TO_TICKS(20));
        waited += 20;
        if (waited > 35000) { ESP_LOGW(TAG, "busy 35s 超时"); break; }
    }
}

// 上电 + 寄存器初始化(规格书 p35 OTP 参考码)
static void ssd1677_panel_init(void)
{
    hal_spi_reset();

    hal_spi_cmd(0x12);              // SWRESET
    vTaskDelay(pdMS_TO_TICKS(10));
    wait_busy();

    hal_spi_cmd(0x0C);             // 升压软启动
    hal_spi_data(0xAE); hal_spi_data(0xC7); hal_spi_data(0xC3);
    hal_spi_data(0xC0); hal_spi_data(0x80);

    hal_spi_cmd(0x01);             // 驱动输出控制: 480 行
    hal_spi_data(0xDF); hal_spi_data(0x01); hal_spi_data(0x02);

    hal_spi_cmd(0x11); hal_spi_data(0x01);   // 数据进入模式

    hal_spi_cmd(0x44);             // RAM X: 0..799
    hal_spi_data(0x00); hal_spi_data(0x00);
    hal_spi_data(0x1F); hal_spi_data(0x03);

    hal_spi_cmd(0x45);             // RAM Y: 479..0
    hal_spi_data(0xDF); hal_spi_data(0x01);
    hal_spi_data(0x00); hal_spi_data(0x00);

    hal_spi_cmd(0x3C); hal_spi_data(0x01);   // 边框
    hal_spi_cmd(0x18); hal_spi_data(0x80);   // 内置温度传感器

    ESP_LOGI(TAG, "panel init done");
}

static void set_ram_counter(void)
{
    hal_spi_cmd(0x4E); hal_spi_data(0x00); hal_spi_data(0x00);   // X counter=0
    hal_spi_cmd(0x4F); hal_spi_data(0xDF); hal_spi_data(0x01);   // Y counter=479
}

void ssd1677_ram_begin(void)
{
    set_ram_counter();
    hal_spi_cmd(0x24);
}

void ssd1677_ram_row(const uint8_t *row)
{
#if SSD_BW_INVERT
    static uint8_t tmp[SSD_ROW_BYTES];
    for (int i = 0; i < SSD_ROW_BYTES; i++) tmp[i] = (uint8_t)~row[i];
    hal_spi_data_buf(tmp, SSD_ROW_BYTES);
#else
    hal_spi_data_buf(row, SSD_ROW_BYTES);
#endif
}

// 写 0x24 整屏(plane = caller 提供的 48000B 帧, 不新分配)
void ssd1677_write_ram(const uint8_t *plane)
{
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++)
        ssd1677_ram_row(plane + y * SSD_ROW_BYTES);
}

// 把整帧写入 0x26(旧 RAM) —— 局刷靠 0x24(新) vs 0x26(旧) 差异翻转,
// 每次刷新后同步, 保证下次局刷基准 = 当前屏上内容。
void ssd1677_sync_old_ram(const uint8_t *plane)
{
    set_ram_counter();
    hal_spi_cmd(0x26);
    for (int y = 0; y < SSD_HEIGHT; y++)
        ssd1677_ram_row(plane + y * SSD_ROW_BYTES);
}

void ssd1677_update_full(void)
{
    hal_spi_cmd(0x22); hal_spi_data(0xF7);
    hal_spi_cmd(0x20);
    vTaskDelay(pdMS_TO_TICKS(10));
    wait_busy();
}

// 快波形局刷: 差异翻转、不闪、快。纯波形触发(0x26 同步由 disp 层做)。
// 波形选 0xCF(Display Mode 2, 不重载 OTP 全刷波形)。真机若有重影/不刷,
// 见 spec §6: 改 0xFF 或经 0x32 写自定义局刷 LUT。
void ssd1677_update_partial(void)
{
    hal_spi_cmd(0x22); hal_spi_data(0xCF);
    hal_spi_cmd(0x20);
    vTaskDelay(pdMS_TO_TICKS(10));
    wait_busy();
}

// ---- display_if_t ----
static esp_err_t disp_init(void)
{
    esp_err_t ret = hal_spi_init(EPD_PIN_MOSI, EPD_PIN_SCLK, EPD_PIN_CS,
                                 EPD_PIN_DC, EPD_PIN_RST, EPD_PIN_BUSY);
    if (ret != ESP_OK) { ESP_LOGE(TAG, "spi init: %s", esp_err_to_name(ret)); return ret; }
    ssd1677_panel_init();
    return ESP_OK;
}

static void disp_get_caps(display_caps_t *out)
{
    out->width        = 480;
    out->height       = 800;
    out->color_model  = DISP_BW;
    out->frame_format = "bw-1plane";
    out->frame_bytes  = 48000;
    out->panel_id     = "bw_426";
}

static esp_err_t disp_show(const uint8_t *frame, size_t len)
{
    if (len < SSD_PLANE_BYTES) {
        ESP_LOGE(TAG, "frame too short: %u < %u", (unsigned)len, SSD_PLANE_BYTES);
        return ESP_ERR_INVALID_ARG;
    }
    s_last_frame = frame;
    ssd1677_write_ram(frame);
    return ESP_OK;
}

static void disp_refresh(void)
{
    ssd1677_update_full();
    if (s_last_frame) ssd1677_sync_old_ram(s_last_frame);   // 全刷后基准=当前帧
}

static void disp_refresh_partial(void)
{
    ssd1677_update_partial();
    if (s_last_frame) ssd1677_sync_old_ram(s_last_frame);   // 局刷后基准=当前帧
}

static void disp_clear(void)
{
    static uint8_t row[SSD_ROW_BYTES];
    memset(row, 0x00, sizeof(row));   // bit=0 => 白(经极性取反后发 0xFF=白)
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);
    ssd1677_update_full();
}

static void disp_sleep(void)
{
    hal_spi_cmd(0x10); hal_spi_data(0x01);   // 深睡
}

extern void ssd1677_selftest_run(void);

static const display_if_t s_if = {
    .init = disp_init, .get_caps = disp_get_caps, .show = disp_show,
    .refresh = disp_refresh, .refresh_partial = disp_refresh_partial,
    .clear = disp_clear, .sleep = disp_sleep,
    .selftest = ssd1677_selftest_run,
};

const display_if_t *ssd1677_driver(void) { return &s_if; }
