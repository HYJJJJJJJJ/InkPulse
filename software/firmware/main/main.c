#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "epd_uc8179.h"

static const char *TAG = "inkpulse";

void app_main(void)
{
    ESP_LOGI(TAG, "boot");
    epd_hal_init();
    epd_init();

    ESP_LOGI(TAG, ">>> 清屏(白) 关键里程碑");
    epd_clear();

    ESP_LOGI(TAG, ">>> 1/5 白"); epd_show_solid(0xFF, 0x00); vTaskDelay(pdMS_TO_TICKS(4000));
    ESP_LOGI(TAG, ">>> 2/5 黑"); epd_show_solid(0x00, 0x00); vTaskDelay(pdMS_TO_TICKS(4000));
    ESP_LOGI(TAG, ">>> 3/5 红"); epd_show_solid(0xFF, 0xFF); vTaskDelay(pdMS_TO_TICKS(4000));
    ESP_LOGI(TAG, ">>> 4/5 上黑下红"); epd_show_split(); vTaskDelay(pdMS_TO_TICKS(4000));
    ESP_LOGI(TAG, ">>> 5/5 棋盘"); epd_show_checker(); vTaskDelay(pdMS_TO_TICKS(4000));

    ESP_LOGI(TAG, ">>> patterns done, sleeping");
    epd_sleep();
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
