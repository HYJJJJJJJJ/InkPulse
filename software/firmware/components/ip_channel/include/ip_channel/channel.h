#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "esp_err.h"
#include "ip_display/display.h"
#include "ip_sensor/sensor.h"

typedef struct { bool changed; int next_refresh_s; } channel_result_t;

typedef struct {
    esp_err_t (*init)(const display_caps_t *caps);   // 知道要拉什么帧格式/字节数
    esp_err_t (*fetch)(uint8_t *buf, size_t buf_len,
                       const sensor_env_t *env, channel_result_t *out);
    // 预留(本期不实现): esp_err_t (*poll_control)(...);
} channel_if_t;

const channel_if_t *http_hub_channel(void);
