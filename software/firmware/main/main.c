#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "htu21d.h"
#include "epd_uc8179.h"

static const char *TAG = "verify";

void app_main(void)
{
    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, "  InkPulse 合并验证: 温湿度 + 屏幕");
    ESP_LOGI(TAG, "==================================================");

    // ---------- 1) 温湿度 (I2C) ----------
    ESP_LOGI(TAG, "[1] HTU21D 温湿度:");
    htu21d_init();
    for (int i = 0; i < 3; i++) {
        float t = 0, h = 0;
        if (htu21d_read(&t, &h))
            ESP_LOGI(TAG, "    温度=%.2f C   湿度=%.2f %%", t, h);
        else
            ESP_LOGW(TAG, "    读取失败");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }

    // ---------- 2) 屏幕 (SPI/UC8179) ----------
    ESP_LOGI(TAG, "[2] 墨水屏: 初始化 + 白/黑/红");
    epd_hal_init();
    epd_init();

    ESP_LOGI(TAG, "    >>> 全白 (该白)"); epd_show_solid(0xFF, 0x00); vTaskDelay(pdMS_TO_TICKS(4000));
    ESP_LOGI(TAG, "    >>> 全黑 (该黑)"); epd_show_solid(0x00, 0x00); vTaskDelay(pdMS_TO_TICKS(4000));
    ESP_LOGI(TAG, "    >>> 全红 (该红)"); epd_show_solid(0xFF, 0xFF); vTaskDelay(pdMS_TO_TICKS(4000));

    ESP_LOGI(TAG, "=== 验证结束 ===");
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
