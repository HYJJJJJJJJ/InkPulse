#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "htu21d.h"
#include "epd_uc8179.h"
#include "wifi_prov.h"
#include "frame_client.h"

static const char *TAG = "inkpulse";

// 定义 INKPULSE_VERIFY(idf.py build -DINKPULSE_VERIFY=1 或在此 #define)
// 可跑阶段一 bring-up harness: 温湿度 + 白/黑/红, 不联网。
#ifdef INKPULSE_VERIFY

void app_main(void)
{
    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, "  InkPulse 合并验证: 温湿度 + 屏幕");
    ESP_LOGI(TAG, "==================================================");

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

    ESP_LOGI(TAG, "[2] 墨水屏: 初始化 + 白/黑/红");
    epd_hal_init();
    epd_init();
    ESP_LOGI(TAG, "    >>> 全白"); epd_show_solid(0xFF, 0x00); vTaskDelay(pdMS_TO_TICKS(4000));
    ESP_LOGI(TAG, "    >>> 全黑"); epd_show_solid(0x00, 0x00); vTaskDelay(pdMS_TO_TICKS(4000));
    ESP_LOGI(TAG, "    >>> 全红"); epd_show_solid(0xFF, 0xFF); vTaskDelay(pdMS_TO_TICKS(4000));
    ESP_LOGI(TAG, "=== 验证结束 ===");
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}

#else  // ---- 联网主循环(默认) ----

void app_main(void)
{
    ESP_LOGI(TAG, "boot");
    epd_hal_init();
    epd_init();
    htu21d_init();

    if (!wifi_connect_or_provision()) {
        // 进入配网模式(配完会自动重启), 给个干净白屏提示
        epd_clear();
        while (1) vTaskDelay(pdMS_TO_TICKS(1000));
    }

    // 联网成功, 首帧前全白清屏一次: 消除阶段一红测试图案的 BWR 红残影(ghosting)。
    // OTP LUT 单次全刷对红粒子清除不彻底, 开机做一次干净 clear 再写仪表盘。
    epd_clear();

    while (1) {
        float t = 0, h = 0;
        bool have_env = htu21d_read(&t, &h);
        int next = 600;
        int r = frame_fetch_and_show(have_env ? t : -100, have_env ? h : -100, &next);
        ESP_LOGI(TAG, "fetch -> %s, next=%ds",
                 r == 1 ? "新帧已刷" : r == 0 ? "未变(304)" : "出错/离线", next);
        if (next < 30) next = 30;          // 下限保护
        vTaskDelay(pdMS_TO_TICKS((uint32_t)next * 1000));
    }
}

#endif
