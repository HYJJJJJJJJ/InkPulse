#pragma once
// 板载 BOOT 键(GPIO0, 低有效) 手势识别。
// 短按(<1s)/长按(>=3s) 各触发一个回调; 回调在按键 task 上下文执行。
typedef void (*button_cb_t)(void);

// 初始化 GPIO0 + 启动手势识别 task。回调可为 NULL。
void button_init(button_cb_t on_short, button_cb_t on_long);
