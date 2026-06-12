#pragma once
#include <stdbool.h>
#include "esp_err.h"

typedef struct {
    float temp_c;    bool temp_valid;
    float humidity;  bool humidity_valid;   // 传感器损坏读 0 时置 false
} sensor_env_t;

typedef struct {
    esp_err_t (*init)(void);
    esp_err_t (*read)(sensor_env_t *out);
} sensor_if_t;

const sensor_if_t *htu21d_sensor(void);
