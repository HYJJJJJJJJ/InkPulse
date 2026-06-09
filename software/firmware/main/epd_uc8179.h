#pragma once
#include <stdint.h>
#include <stddef.h>

void epd_hal_init(void);                 // 初始化 SPI + GPIO
void epd_reset(void);                    // 硬复位
void epd_send_cmd(uint8_t cmd);          // DC=0 发命令
void epd_send_data(uint8_t data);        // DC=1 发单字节
void epd_send_data_buf(const uint8_t *buf, size_t len); // DC=1 发缓冲
void epd_wait_busy(void);                // 等 BUSY_N 回高(空闲)

void epd_init(void);                     // UC8179 初始化序列
void epd_fill_plane(uint8_t cmd, uint8_t value); // 用常量填满一个 plane(48000B)
void epd_refresh(void);                  // DRF + 等忙
void epd_clear(void);                    // 清成白
void epd_sleep(void);                    // 深睡

// 测试图案(bring-up 验证颜色极性与方向)
void epd_show_solid(uint8_t bw_val, uint8_t red_val); // 纯色:两plane常量
void epd_show_split(void);     // 上半黑 下半红
void epd_show_checker(void);   // 棋盘(黑/白) 验证方向与寻址
