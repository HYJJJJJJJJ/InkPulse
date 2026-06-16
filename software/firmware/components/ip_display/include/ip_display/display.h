#pragma once
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

typedef enum { DISP_BWR, DISP_BW, DISP_ACEP7, DISP_RGB } disp_color_model_t;

typedef struct {
    uint16_t width, height;
    disp_color_model_t color_model;
    const char *frame_format;   // 如 "bwr-dualplane"
    size_t frame_bytes;
    const char *panel_id;       // 上报给 hub 的 profile id, 如 "bwr_750"/"bw_426"; 可空
} display_caps_t;

typedef struct {
    esp_err_t (*init)(void);
    void      (*get_caps)(display_caps_t *out);
    esp_err_t (*show)(const uint8_t *frame, size_t len);  // frame = black(48000)+red(48000)
    void      (*refresh)(void);
    void      (*refresh_partial)(void);   // 局刷; NULL=驱动不支持, 主循环回退全刷
    void      (*clear)(void);
    void      (*sleep)(void);
    void      (*selftest)(void);   // bring-up 图案(白/黑/红/分屏/棋盘)
} display_if_t;

const display_if_t *uc8179_driver(void);
const display_if_t *ssd1677_driver(void);
