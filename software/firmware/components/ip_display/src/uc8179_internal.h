#pragma once
// uc8179 内部共享声明 —— 不进 public include/
// uc8179.c 与 uc8179_selftest.c 共用
#include <stdint.h>
#include <stddef.h>

// 屏幕尺寸常量 (不暴露到 display.h)
#define EPD_WIDTH       800
#define EPD_HEIGHT      480
#define EPD_ROW_BYTES   (EPD_WIDTH / 8)               // 100
#define EPD_PLANE_BYTES (EPD_ROW_BYTES * EPD_HEIGHT)   // 48000

// 0x13(RED): EPD_RED_INVERT=0 => 直发(bit=1->红); 改1则取反
#define EPD_RED_INVERT  0

// uc8179.c 暴露给 selftest 的内部辅助函数
void uc8179_fill_plane(uint8_t cmd, uint8_t value);   // 用常量填满一个 plane
void uc8179_refresh(void);                             // DRF + 等忙
