idf_component_register(
    SRCS
        "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        driver             # spi_master / gpio
        esp_driver_i2c     # i2c_master (HTU21D)
        esp_wifi
        esp_event
        esp_netif
        esp_http_server    # SoftAP 配网页
        nvs_flash          # WiFi 凭据持久化
        ip_config          # 编译期网络常量头
        ip_hal             # 硬件抽象层(SPI/I2C/GPIO)
        ip_display         # 墨水屏驱动(display 接口 + UC8179 实现)
        ip_sensor          # 温湿度传感器接口(sensor_if + HTU21D 实现)
        ip_net             # WiFi STA 连接(WPA3-SAE + 循环重连)
        ip_provisioning    # BLE/SoftAP 配网 + NVS 凭据
        ip_channel         # HTTP-Hub 数据源(channel 接口 + HTTP 实现)
)

# 把 idf.py -DINKPULSE_VERIFY=1 的 CMake 变量转成 C 编译宏, 否则 main.c 的
# #ifdef INKPULSE_VERIFY 看不到它(bring-up 验证模式: 温湿度 + 测试图案, 不联网)。
if(INKPULSE_VERIFY)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE INKPULSE_VERIFY=1)
endif()
