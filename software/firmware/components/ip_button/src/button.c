#include "ip_button/button.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "button";

#define BTN_GPIO       0       // BOOT 键
#define POLL_MS        20      // 轮询周期(兼做消抖)
#define DEBOUNCE_N     2       // 释放需连续 N 次稳定高电平才确认
#define SHORT_MAX_MS   1000    // 短按上限
#define LONG_MS        3000    // 长按阈值(触发即回调, 不等释放)

static button_cb_t s_short, s_long;

static void button_task(void *arg)
{
    bool pressed = false;
    int  press_ms = 0;
    bool long_fired = false;
    int  release_cnt = 0;

    while (1) {
        bool down = (gpio_get_level(BTN_GPIO) == 0);   // 低=按下

        if (down) {
            release_cnt = 0;
            if (!pressed) {
                pressed = true; press_ms = 0; long_fired = false;
            } else {
                press_ms += POLL_MS;
                if (!long_fired && press_ms >= LONG_MS) {
                    long_fired = true;
                    ESP_LOGI(TAG, "长按 -> 配网");
                    if (s_long) s_long();
                }
            }
        } else if (pressed) {
            // 消抖: 需连续 DEBOUNCE_N 次高电平才认定释放
            if (++release_cnt >= DEBOUNCE_N) {
                pressed = false;
                if (!long_fired && press_ms < SHORT_MAX_MS) {
                    ESP_LOGI(TAG, "短按 -> 刷新");
                    if (s_short) s_short();
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(POLL_MS));
    }
}

void button_init(button_cb_t on_short, button_cb_t on_long)
{
    s_short = on_short;
    s_long  = on_long;
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << BTN_GPIO,
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&io);
    xTaskCreate(button_task, "button", 2560, NULL, 5, NULL);
    ESP_LOGI(TAG, "button init (GPIO%d, 短按<%dms / 长按>=%dms)",
             BTN_GPIO, SHORT_MAX_MS, LONG_MS);
}
