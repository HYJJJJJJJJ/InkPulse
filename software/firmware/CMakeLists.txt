# InkPulse 固件 (ESP32-S3 + UC8179 BWR 墨水屏)
# 标准 ESP-IDF 工程入口, 跨平台(Linux/macOS/Windows)由 idf.py 驱动。
cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(inkpulse)
