// SSD1677 bring-up selftest: 全白 / 全黑 / 竖条 / 棋盘, 用于真机校准极性与旋转。
// 行式流写(仅 100B 行缓冲), 不占整屏 .bss。
#include "ssd1677_internal.h"
#include "ip_hal/spi_bus.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "ssd1677_test";

void ssd1677_selftest_run(void)
{
    static uint8_t row[SSD_ROW_BYTES];   // 100B, bit=1=黑(与 hub 同约定)

    // 全白
    ESP_LOGI(TAG, "图案: 全白");
    memset(row, 0x00, sizeof(row));
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);
    ssd1677_update_full();
    vTaskDelay(pdMS_TO_TICKS(2000));

    // 全黑
    ESP_LOGI(TAG, "图案: 全黑");
    memset(row, 0xFF, sizeof(row));
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);
    ssd1677_update_full();
    vTaskDelay(pdMS_TO_TICKS(2000));

    // 竖条(每行相同: 每 2 字节黑白交替)
    ESP_LOGI(TAG, "图案: 竖条");
    for (int b = 0; b < SSD_ROW_BYTES; b++) row[b] = ((b / 2) & 1) ? 0xFF : 0x00;
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);
    ssd1677_update_full();
    vTaskDelay(pdMS_TO_TICKS(2000));

    // 棋盘(行随 y 变化)
    ESP_LOGI(TAG, "图案: 棋盘");
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++) {
        for (int b = 0; b < SSD_ROW_BYTES; b++)
            row[b] = (((y / 8) + (b / 2)) & 1) ? 0xFF : 0x00;
        ssd1677_ram_row(row);
    }
    ssd1677_update_full();
    vTaskDelay(pdMS_TO_TICKS(2000));

    // ---- 局刷校验: 全刷基准 → 连续局刷走动方块 → 观察不闪/残影/到 30 次洗净 ----
    ESP_LOGI(TAG, "局刷校验: 全刷基准(全白)");
    memset(row, 0x00, sizeof(row));
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);
    ssd1677_update_full();
    // 0x26 基准 = 全白
    set_ram_counter();
    hal_spi_cmd(0x26);
    memset(row, 0x00, sizeof(row));
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);

    for (int i = 0; i < 35; i++) {
        ESP_LOGI(TAG, "局刷 #%d", i + 1);
        // 写 0x24 = 新帧(第 i 个位置一个黑块)
        ssd1677_ram_begin();   // set counter + 0x24
        for (int y = 0; y < SSD_HEIGHT; y++) {
            for (int b = 0; b < SSD_ROW_BYTES; b++)
                row[b] = (y / 40 == 2 && b == (i % SSD_ROW_BYTES)) ? 0xFF : 0x00;
            ssd1677_ram_row(row);
        }
        ssd1677_update_partial();   // 快波形局刷
        // 写 0x26 = 同一帧, 作下一轮基准
        set_ram_counter();
        hal_spi_cmd(0x26);
        for (int y = 0; y < SSD_HEIGHT; y++) {
            for (int b = 0; b < SSD_ROW_BYTES; b++)
                row[b] = (y / 40 == 2 && b == (i % SSD_ROW_BYTES)) ? 0xFF : 0x00;
            ssd1677_ram_row(row);
        }
        vTaskDelay(pdMS_TO_TICKS(700));
    }

    ESP_LOGI(TAG, "selftest 结束");
}
