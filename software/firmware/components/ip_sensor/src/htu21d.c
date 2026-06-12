#include "ip_sensor/sensor.h"
#include "ip_hal/i2c_bus.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#define HTU_SDA          1
#define HTU_SCL          2
#define HTU_ADDR         0x40
#define CMD_T_NOHOLD     0xF3
#define CMD_H_NOHOLD     0xF5
#define CMD_SOFT_RESET   0xFE

static const char *TAG = "htu21d";

static esp_err_t htu_init(void)
{
    esp_err_t ret = hal_i2c_init(HTU_SDA, HTU_SCL, HTU_ADDR);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "hal_i2c_init 失败: %s", esp_err_to_name(ret));
        return ret;
    }

    // 软复位(0xFE): 把用户寄存器重置到默认(RH12/T14)。排查湿度通道读全 0 的异常。
    uint8_t soft_reset = CMD_SOFT_RESET;
    esp_err_t re = hal_i2c_write(&soft_reset, 1, 200);
    ESP_LOGI(TAG, "软复位 0xFE: %s", esp_err_to_name(re));
    vTaskDelay(pdMS_TO_TICKS(20));   // 软复位耗时 <15ms

    ESP_LOGI(TAG, "I2C init (SCL=%d SDA=%d addr=0x%02X)", HTU_SCL, HTU_SDA, HTU_ADDR);
    return ESP_OK;
}

static bool measure(uint8_t cmd, uint16_t *raw)
{
    esp_err_t e = hal_i2c_write(&cmd, 1, 200);
    if (e != ESP_OK) {
        ESP_LOGW(TAG, "transmit cmd 0x%02X 失败: %s", cmd, esp_err_to_name(e));
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(60));  // 14-bit 测量约 50ms
    uint8_t rx[3] = {0};
    e = hal_i2c_read(rx, 3, 200);
    if (e != ESP_OK) {
        ESP_LOGW(TAG, "receive 失败: %s", esp_err_to_name(e));
        return false;
    }
    *raw = ((uint16_t)rx[0] << 8 | rx[1]) & 0xFFFC;
    ESP_LOGI(TAG, "cmd=0x%02X rx=[%02X %02X %02X] raw=%u", cmd, rx[0], rx[1], rx[2], *raw);
    return true;
}

static esp_err_t htu_read(sensor_env_t *out)
{
    uint16_t rt = 0, rh = 0;
    bool t_ok = measure(CMD_T_NOHOLD, &rt);
    bool h_ok = measure(CMD_H_NOHOLD, &rh);

    // 温度
    if (t_ok) {
        out->temp_c    = -46.85f + 175.72f * rt / 65536.0f;
        out->temp_valid = true;
    } else {
        out->temp_c    = 0.0f;
        out->temp_valid = false;
    }

    // 湿度: raw==0 视为传感器损坏(硬件异常), 标 invalid
    if (h_ok && rh != 0) {
        out->humidity       = -6.0f + 125.0f * rh / 65536.0f;
        out->humidity_valid = true;
    } else {
        out->humidity       = 0.0f;
        out->humidity_valid = false;
    }

    if (!t_ok && !h_ok) return ESP_FAIL;
    return ESP_OK;
}

static const sensor_if_t s_if = { .init = htu_init, .read = htu_read };

const sensor_if_t *htu21d_sensor(void) { return &s_if; }
