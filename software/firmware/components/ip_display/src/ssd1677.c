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

static bool wait_busy(void)
{
    // SSD1677 BUSY: 高=忙(规格书 5-4)。等到低电平。
    int waited = 0;
    while (hal_spi_busy_level() == 1) {
        vTaskDelay(pdMS_TO_TICKS(20));
        waited += 20;
        if (waited > 35000) { ESP_LOGW(TAG, "busy 35s 超时"); return false; }
    }
    return true;
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

void ssd1677_set_ram_counter(void)
{
    hal_spi_cmd(0x4E); hal_spi_data(0x00); hal_spi_data(0x00);   // X counter=0
    hal_spi_cmd(0x4F); hal_spi_data(0xDF); hal_spi_data(0x01);   // Y counter=479
}

void ssd1677_ram_begin(void)
{
    ssd1677_set_ram_counter();
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
    ssd1677_set_ram_counter();
    hal_spi_cmd(0x26);
    for (int y = 0; y < SSD_HEIGHT; y++)
        ssd1677_ram_row(plane + y * SSD_ROW_BYTES);
}

bool ssd1677_update_full(void)
{
    hal_spi_cmd(0x3C); hal_spi_data(0x01);   // 恢复实心边框(局刷会改成 0xC0 HiZ)
    hal_spi_cmd(0x22); hal_spi_data(0xF7);    // 0xF7: 含从 OTP 重载全刷 LUT
    hal_spi_cmd(0x20);
    vTaskDelay(pdMS_TO_TICKS(10));
    return wait_busy();
}

// 局刷波形 LUT(写入 0x32, 105B)。来源: GxEPD2 GxEPD2_370_TC1.cpp(同芯片 SSD1677,
// SSD168x 兼容命令集)。该屏为 3.7", 本屏 4.26" 借用同芯片波形, timing 段([50-59])
// 真机若重影/对比不足需微调。前 50B=电压模式, 中 50B=TP/RP 时序, 末 5B=gate/source。
static const uint8_t ssd1677_lut_partial[105] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x01, 0x2A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x0A, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x05, 0x05, 0x00, 0x05, 0x03, 0x05, 0x05, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x22, 0x22, 0x22, 0x22, 0x22,
};

// 快波形局刷: 差异翻转、不闪、快。纯波形触发(0x26 同步由 disp 层做)。
// 关键: 必须先往 0x32 灌局刷 LUT(覆盖上次全刷从 OTP 载入的全刷 LUT), 否则 0xCF
// 复用全刷 LUT → 整屏黑闪。0xCF 的 bit4=0 表示"不从 OTP 重载", 故用我们刚写入的局刷 LUT。
bool ssd1677_update_partial(void)
{
    hal_spi_cmd(0x3C); hal_spi_data(0xC0);                 // 边框 HiZ(局刷不刷边框)
    hal_spi_cmd(0x32);                                     // 写局刷 LUT
    hal_spi_data_buf(ssd1677_lut_partial, sizeof(ssd1677_lut_partial));
    hal_spi_cmd(0x22); hal_spi_data(0xCF);                 // Mode2, 不重载 OTP
    hal_spi_cmd(0x20);
    vTaskDelay(pdMS_TO_TICKS(10));
    return wait_busy();
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
    if (ssd1677_update_full() && s_last_frame) ssd1677_sync_old_ram(s_last_frame);
}

static void disp_refresh_partial(void)
{
    if (ssd1677_update_partial() && s_last_frame) ssd1677_sync_old_ram(s_last_frame);
}

static void disp_clear(void)
{
    static uint8_t row[SSD_ROW_BYTES];
    memset(row, 0x00, sizeof(row));   // bit=0 => 白(经极性取反后发 0xFF=白)
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);
    if (ssd1677_update_full()) {       // 全刷成功才同步 0x26 基准=全白
        ssd1677_set_ram_counter();
        hal_spi_cmd(0x26);
        for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);
    }
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
