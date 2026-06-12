idf_component_register(
    SRCS "src/http_hub.c"
    INCLUDE_DIRS "include"
    REQUIRES ip_display ip_sensor ip_config esp_http_client
)
