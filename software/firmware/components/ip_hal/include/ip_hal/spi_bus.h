#pragma once
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

// EPD 用的 SPI: 初始化总线 + DC/RST/CS/BUSY 引脚; 传输由下面函数封装
esp_err_t hal_spi_init(int mosi, int sclk, int cs, int dc, int rst, int busy);
void hal_spi_cmd(uint8_t cmd);                         // DC=0 发命令
void hal_spi_data(uint8_t data);                       // DC=1 发单字节
void hal_spi_data_buf(const uint8_t *buf, size_t len); // DC=1 发缓冲
void hal_spi_reset(void);                              // 复位时序
int  hal_spi_busy_level(void);                         // 读 BUSY 脚电平
