idf_component_register(
    SRCS app_main.cpp board.cpp render_task.cpp touch_task.cpp audio_task.cpp net_task.cpp config_store.cpp
    PRIV_REQUIRES grokwatch_core esp_app_format esp_timer esp_event esp_netif esp_wifi nvs_flash esp_hw_support
)
target_compile_features(${COMPONENT_LIB} PRIVATE cxx_std_17)
