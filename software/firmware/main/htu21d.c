#include "htu21d.h"
#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#define HTU_SDA   1
#define HTU_SCL   2
#define HTU_ADDR  0x40
#define CMD_T_NOHOLD 0xF3
#define CMD_H_NOHOLD 0xF5

static const char *TAG = "htu21d";
static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_dev;

void htu21d_init(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = HTU_SDA,
        .scl_io_num = HTU_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &s_bus));
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = HTU_ADDR,
        .scl_speed_hz = 100000,
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(s_bus, &dev_cfg, &s_dev));
    ESP_LOGI(TAG, "I2C init (SCL=%d SDA=%d addr=0x%02X)", HTU_SCL, HTU_SDA, HTU_ADDR);
}

static bool measure(uint8_t cmd, uint16_t *raw)
{
    esp_err_t e = i2c_master_transmit(s_dev, &cmd, 1, 200);
    if (e != ESP_OK) {
        ESP_LOGW(TAG, "transmit cmd 0x%02X 失败: %s", cmd, esp_err_to_name(e));
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(60));  // 14-bit 测量约 50ms
    uint8_t rx[3] = {0};
    e = i2c_master_receive(s_dev, rx, 3, 200);
    if (e != ESP_OK) {
        ESP_LOGW(TAG, "receive 失败: %s", esp_err_to_name(e));
        return false;
    }
    *raw = ((uint16_t)rx[0] << 8 | rx[1]) & 0xFFFC;
    return true;
}

bool htu21d_read(float *temp_c, float *humidity)
{
    uint16_t rt, rh;
    if (!measure(CMD_T_NOHOLD, &rt)) return false;
    if (!measure(CMD_H_NOHOLD, &rh)) return false;
    *temp_c = -46.85f + 175.72f * rt / 65536.0f;
    *humidity = -6.0f + 125.0f * rh / 65536.0f;
    return true;
}
