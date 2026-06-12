#pragma once
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

esp_err_t hal_i2c_init(int sda, int scl, uint8_t addr_7b);
esp_err_t hal_i2c_write(const uint8_t *data, size_t len, int timeout_ms);
esp_err_t hal_i2c_read(uint8_t *data, size_t len, int timeout_ms);
