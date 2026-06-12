idf_component_register(
    SRCS "src/spi_bus.c" "src/i2c_bus.c"
    INCLUDE_DIRS "include"
    REQUIRES driver esp_driver_i2c
)
