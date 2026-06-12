// UC8179 自测图案: 依次全白→全黑→全红→分屏→棋盘格
// 每个图案之间间隔 4s, 用于 bring-up 验证颜色极性与方向
#include "uc8179_internal.h"
#include "ip_hal/spi_bus.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "uc8179_selftest";

// 全白 / 全黑 / 全红 等纯色填充
static void show_solid(uint8_t bw_val, uint8_t red_val)
{
    uc8179_fill_plane(0x10, bw_val);
    uc8179_fill_plane(0x13, red_val);
    uc8179_refresh();
}

// 上半黑 下半白 + 下半叠红
static void show_split(void)
{
    static uint8_t row[EPD_ROW_BYTES];

    // B/W plane: 上半黑(0x00) 下半白(0xFF)
    hal_spi_cmd(0x10);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        memset(row, (y < EPD_HEIGHT / 2) ? 0x00 : 0xFF, sizeof(row));
        hal_spi_data_buf(row, sizeof(row));
    }
    // RED plane: 上半不红(0x00) 下半红(0xFF)
    hal_spi_cmd(0x13);
    for (int y = 0; y < EPD_HEIGHT; y++) {
        memset(row, (y < EPD_HEIGHT / 2) ? 0x00 : 0xFF, sizeof(row));
        hal_spi_data_buf(row, sizeof(row));
    }
    uc8179_refresh();
}

// 棋盘格(黑/白) 验证行列寻址; 红 plane 填 0
static void show_checker(void)
{
    static uint8_t row[EPD_ROW_BYTES];

    hal_spi_cmd(0x10);  // 64px 方格: 行带与列带异或
    for (int y = 0; y < EPD_HEIGHT; y++) {
        uint8_t band = (y / 64) & 1;
        for (int xb = 0; xb < EPD_ROW_BYTES; xb++) {
            uint8_t col = ((xb * 8) / 64) & 1;
            row[xb] = (band ^ col) ? 0x00 : 0xFF;  // 黑/白交替
        }
        hal_spi_data_buf(row, sizeof(row));
    }
    uc8179_fill_plane(0x13, 0x00);  // 无红
    uc8179_refresh();
}

void uc8179_selftest_run(void)
{
    ESP_LOGI(TAG, ">>> 全白");
    show_solid(0xFF, 0x00);
    vTaskDelay(pdMS_TO_TICKS(4000));

    ESP_LOGI(TAG, ">>> 全黑");
    show_solid(0x00, 0x00);
    vTaskDelay(pdMS_TO_TICKS(4000));

    ESP_LOGI(TAG, ">>> 全红");
    show_solid(0xFF, 0xFF);
    vTaskDelay(pdMS_TO_TICKS(4000));

    ESP_LOGI(TAG, ">>> 上黑下白 / 上不红下红(分屏: 验方向与极性)");
    show_split();
    vTaskDelay(pdMS_TO_TICKS(4000));

    ESP_LOGI(TAG, ">>> 棋盘格(验行列寻址)");
    show_checker();
    vTaskDelay(pdMS_TO_TICKS(4000));

    ESP_LOGI(TAG, "selftest done");
}
