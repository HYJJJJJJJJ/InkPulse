#pragma once
#include <stdbool.h>
#include "ip_display/display.h"

// 拉一帧: 带 If-None-Match(上次 etag) + 温湿度查询。
// disp: 屏驱动接口指针(解耦屏驱动实现)。
// 返回: 1=有新帧已写屏, 0=304 未变, -1=出错(保留上一帧)。
// next_refresh_s 写出下次刷新间隔(秒)。
int frame_fetch_and_show(const display_if_t *disp, float temp_c, float humidity, int *next_refresh_s);
