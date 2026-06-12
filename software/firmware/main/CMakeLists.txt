idf_component_register(
    SRCS
        "main.c"
        "epd_uc8179.c"
        "htu21d.c"
        "wifi_prov.c"
        "ble_prov.c"
        "frame_client.c"
    INCLUDE_DIRS "."
    REQUIRES
        driver             # spi_master / gpio
        esp_driver_i2c     # i2c_master (HTU21D)
        esp_wifi
        esp_event
        esp_netif
        esp_http_client    # 拉帧
        esp_http_server    # SoftAP 配网页
        nvs_flash          # WiFi 凭据持久化
        wifi_provisioning  # BLE 配网
        bt                 # NimBLE
        ip_config          # 编译期网络常量头
)

# 把 idf.py -DINKPULSE_VERIFY=1 的 CMake 变量转成 C 编译宏, 否则 main.c 的
# #ifdef INKPULSE_VERIFY 看不到它(bring-up 验证模式: 温湿度 + 测试图案, 不联网)。
if(INKPULSE_VERIFY)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE INKPULSE_VERIFY=1)
endif()
