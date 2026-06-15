#pragma once
// ssd1677 内部共享声明 —— 不进 public include/
#include <stdint.h>
#include <stddef.h>

#define SSD_WIDTH       800     // 控制器 RAM 源方向(hub 旋转后宽)
#define SSD_HEIGHT      480     // 控制器 RAM 栅方向
#define SSD_ROW_BYTES   (SSD_WIDTH / 8)               // 100
#define SSD_PLANE_BYTES (SSD_ROW_BYTES * SSD_HEIGHT)   // 48000

// 0x24 BW RAM: 1=白/0=黑(常约定)。hub bit=1=黑, 故默认取反发送。真机不对改 0。
#define SSD_BW_INVERT   1

// 暴露给 selftest 的内部辅助
void ssd1677_write_ram(const uint8_t *plane);   // 写 0x24 整屏(48000B 概念帧, bit=1=黑, 内部按极性处理)
void ssd1677_update_full(void);                  // 0x22(0xF7)+0x20 全刷 + 等忙
