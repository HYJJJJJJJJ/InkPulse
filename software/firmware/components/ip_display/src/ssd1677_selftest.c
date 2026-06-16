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

    // ---- 区域局刷验证: 全白基准 → 只在中间 100 栅行窗口里翻黑/白 → 看窗口外白底是否保持 ----
    // 假设: SSD1677 标准局刷重刷"窗口内"每个像素, 故只要把窗口收到变化区, 窗口外就不通电、
    // 不会累积发灰。若窗口外保持白 → 证明"区域局刷"是消灰正解(方案 B)。
    ESP_LOGI(TAG, "区域局刷验证: 全刷基准(全白)");
    memset(row, 0x00, sizeof(row));
    ssd1677_ram_begin();
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);
    ssd1677_update_full();
    ssd1677_set_ram_counter();              // 0x26 基准 = 全白
    hal_spi_cmd(0x26);
    for (int y = 0; y < SSD_HEIGHT; y++) ssd1677_ram_row(row);

    const int wy_lo = 190, wy_hi = 289, wn = wy_hi - wy_lo + 1;   // 中间 100 栅行
    for (int i = 0; i < 20; i++) {
        uint8_t v = (i & 1) ? 0xFF : 0x00;   // 窗口内交替: 黑/白
        ESP_LOGI(TAG, "区域局刷 #%d (窗内%s, 窗外应恒白)", i + 1, v ? "黑" : "白");
        ssd1677_set_window_rows(wy_lo, wy_hi);   // 窗口=中间 100 行
        hal_spi_cmd(0x24);
        memset(row, v, sizeof(row));
        for (int y = 0; y < wn; y++) ssd1677_ram_row(row);
        ssd1677_update_partial();
        ssd1677_set_window_rows(wy_lo, wy_hi);   // 同步 0x26 同窗口
        hal_spi_cmd(0x26);
        for (int y = 0; y < wn; y++) ssd1677_ram_row(row);
        vTaskDelay(pdMS_TO_TICKS(800));
    }
    ssd1677_set_window_rows(0, SSD_HEIGHT - 1);   // 恢复整屏窗口

    ESP_LOGI(TAG, "selftest 结束");
}
