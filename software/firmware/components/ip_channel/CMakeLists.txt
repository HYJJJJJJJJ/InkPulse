idf_component_register(
    SRCS "src/http_hub.c"
    INCLUDE_DIRS "include"
    REQUIRES ip_display ip_sensor ip_config ip_provisioning esp_http_client esp_netif esp_wifi mdns
)
