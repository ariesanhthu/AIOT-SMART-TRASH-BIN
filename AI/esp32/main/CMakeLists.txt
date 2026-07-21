idf_component_register(
    SRCS
        "app_main.cpp"
        "camera_adapter.cpp"
        "image_preprocessor.cpp"
        "status.cpp"
        "tflm_classifier.cpp"
        "model/model_data.cc"
    INCLUDE_DIRS
        "."
        "model"
    PRIV_REQUIRES
        esp_timer
        heap
)

target_compile_features(${COMPONENT_LIB} PUBLIC cxx_std_17)
target_compile_options(${COMPONENT_LIB} PRIVATE -O3 -Werror=return-type)
