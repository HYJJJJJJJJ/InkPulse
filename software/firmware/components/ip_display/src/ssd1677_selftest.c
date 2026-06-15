// SSD1677 bring-up selftest: 全白 / 全黑 / 竖条 / 棋盘, 用于真机校准极性与旋转。
#include "ssd1677_internal.h"
#include "ip_hal/spi_bus.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "ssd1677_test";
static uint8_t s_plane[SSD_PLANE_BYTES];   // 概念帧: bit=1=黑(与 hub 同约定)

static void show(const char *name)
{
    ESP_LOGI(TAG, "图案: %s", name);
    ssd1677_write_ram(s_plane);
    ssd1677_update_full();
    vTaskDelay(pdMS_TO_TICKS(2000));
}

void ssd1677_selftest_run(void)
{
    memset(s_plane, 0x00, sizeof(s_plane)); show("全白");      // bit=0 => 白
    memset(s_plane, 0xFF, sizeof(s_plane)); show("全黑");      // bit=1 => 黑

    for (int y = 0; y < SSD_HEIGHT; y++)
        for (int b = 0; b < SSD_ROW_BYTES; b++)
            s_plane[y*SSD_ROW_BYTES + b] = ((b/2) & 1) ? 0xFF : 0x00;
    show("竖条");

    for (int y = 0; y < SSD_HEIGHT; y++)
        for (int b = 0; b < SSD_ROW_BYTES; b++)
            s_plane[y*SSD_ROW_BYTES + b] = ((y/8 + b/2) & 1) ? 0xFF : 0x00;
    show("棋盘");

    ESP_LOGI(TAG, "selftest 结束");
}
