idf_component_register(
    SRCS "src/ble_prov.c" "src/softap_prov.c" "src/creds_nvs.c"
    INCLUDE_DIRS "include"
    REQUIRES ip_net ip_config wifi_provisioning bt esp_http_server nvs_flash esp_wifi
)
