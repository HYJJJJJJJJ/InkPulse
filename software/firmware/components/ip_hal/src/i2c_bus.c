// ip_hal/i2c_bus.c — I2C 总线 HAL
// 从 main/htu21d.c 抽取 I2C 初始化/读写部分封装
#include "ip_hal/i2c_bus.h"
#include "driver/i2c_master.h"
#include "esp_log.h"

static const char *TAG = "hal_i2c";

static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_dev;

esp_err_t hal_i2c_init(int sda, int scl, uint8_t addr_7b)
{
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port                = I2C_NUM_0,
        .sda_io_num              = sda,
        .scl_io_num              = scl,
        .clk_source              = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt       = 7,
        .flags.enable_internal_pullup = true,
    };
    esp_err_t err = i2c_new_master_bus(&bus_cfg, &s_bus);
    if (err != ESP_OK) return err;

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address  = addr_7b,
        .scl_speed_hz    = 100000,  // 100kHz
    };
    err = i2c_master_bus_add_device(s_bus, &dev_cfg, &s_dev);
    if (err != ESP_OK) return err;

    ESP_LOGI(TAG, "hal_i2c_init done (sda=%d scl=%d addr=0x%02X)", sda, scl, addr_7b);
    return ESP_OK;
}

esp_err_t hal_i2c_write(const uint8_t *data, size_t len, int timeout_ms)
{
    return i2c_master_transmit(s_dev, data, len, timeout_ms);
}

esp_err_t hal_i2c_read(uint8_t *data, size_t len, int timeout_ms)
{
    return i2c_master_receive(s_dev, data, len, timeout_ms);
}
