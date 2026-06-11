idf_component_register(
    SRCS
        "main.c"
        "epd_uc8179.c"
        "htu21d.c"
        "wifi_prov.c"
        "frame_client.c"
    INCLUDE_DIRS "."
    REQUIRES
        driver           # spi_master / gpio
        esp_driver_i2c   # i2c_master (HTU21D)
        esp_wifi
        esp_event
        esp_netif
        esp_http_client  # 拉帧
        esp_http_server  # SoftAP 配网页
        nvs_flash        # WiFi 凭据持久化
)
