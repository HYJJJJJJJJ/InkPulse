#pragma once
// ssd1677 内部共享声明 —— 不进 public include/
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define SSD_WIDTH       800     // 控制器 RAM 源方向(hub 旋转后宽)
#define SSD_HEIGHT      480     // 控制器 RAM 栅方向
#define SSD_ROW_BYTES   (SSD_WIDTH / 8)               // 100
#define SSD_PLANE_BYTES (SSD_ROW_BYTES * SSD_HEIGHT)   // 48000

// 0x24 BW RAM: 1=白/0=黑(常约定)。hub bit=1=黑, 故默认取反发送。真机不对改 0。
#define SSD_BW_INVERT   1

// 暴露给 selftest 的内部辅助
void ssd1677_write_ram(const uint8_t *plane);   // 写 0x24 整屏(48000B 概念帧, bit=1=黑, 内部按极性)
bool ssd1677_update_full(void);                  // 0x22(0xF7)+0x20 全刷 + 等忙; 返回 false=超时
void ssd1677_ram_begin(void);                    // set RAM counter + 发 0x24, 准备流式写行
void ssd1677_ram_row(const uint8_t *row);        // 发一行(SSD_ROW_BYTES=100B, bit=1=黑, 内部按极性)
bool ssd1677_update_partial(void);                 // 0x22(0xCF)+0x20 快波形局刷 + 等忙; 返回 false=超时
void ssd1677_sync_old_ram(const uint8_t *plane);   // 把当前帧写入 0x26(下次局刷基准), 行式流写
void ssd1677_set_ram_counter(void);   // set RAM X/Y counter 到原点(供 selftest 写 0x26)
