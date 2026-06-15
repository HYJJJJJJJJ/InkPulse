idf_component_register(
    SRCS "src/uc8179.c" "src/uc8179_selftest.c" "src/ssd1677.c" "src/ssd1677_selftest.c"
    INCLUDE_DIRS "include"
    REQUIRES ip_hal ip_config
)
