idf_component_register(
    SRCS
        "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        # main 只依赖接口 component; 具体 ESP-IDF 依赖(driver/wifi/nvs/...)已下沉到各 component 内部
        ip_config          # 编译期常量头
        ip_display         # 墨水屏(display 接口 + UC8179 实现)
        ip_sensor          # 温湿度(sensor 接口 + HTU21D 实现)
        ip_net             # WiFi STA(WPA3-SAE + 循环重连)
        ip_provisioning    # BLE/SoftAP 配网 + NVS 凭据
        ip_channel         # HTTP-Hub 数据源(channel 接口 + HTTP 实现)
        ip_button          # BOOT 键(GPIO0) 短按刷新 / 长按配网
)

# 把 idf.py -DINKPULSE_VERIFY=1 的 CMake 变量转成 C 编译宏, 否则 main.c 的
# #ifdef INKPULSE_VERIFY 看不到它(bring-up 验证模式: 温湿度 + 测试图案, 不联网)。
if(INKPULSE_VERIFY)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE INKPULSE_VERIFY=1)
endif()
