#pragma once
#include <stdbool.h>
// HTU21D 温湿度 (I2C: SCL=GPIO2, SDA=GPIO1, addr 0x40)
void htu21d_init(void);
// 读温湿度; 成功返回 true, 温度℃/湿度% 写入出参
bool htu21d_read(float *temp_c, float *humidity);
