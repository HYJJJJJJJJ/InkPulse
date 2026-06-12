#pragma once
// E075A42 (UC8179) <-> ESP32-S3 引脚映射，来自原理图 net label 坐标逐行对齐确认
#define EPD_PIN_SCLK   41   // SCL
#define EPD_PIN_MOSI   42   // SDA
#define EPD_PIN_CS     40   // CSB
#define EPD_PIN_DC     39   // DC
#define EPD_PIN_RST    38   // RES
#define EPD_PIN_BUSY   37   // BUSY_N (低=忙)

#define EPD_WIDTH       800
#define EPD_HEIGHT      480
#define EPD_ROW_BYTES   (EPD_WIDTH / 8)            // 100
#define EPD_PLANE_BYTES (EPD_ROW_BYTES * EPD_HEIGHT) // 48000
