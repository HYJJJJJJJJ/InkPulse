idf_component_register(
    SRCS "src/net_sta.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_wifi esp_event esp_netif nvs_flash
)
