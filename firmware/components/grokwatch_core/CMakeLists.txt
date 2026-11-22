set(sources src/avatar_state.cpp src/audio_level.cpp src/link_supervisor.cpp src/protocol.cpp
            src/gesture.cpp src/gaze.cpp src/blink.cpp src/drift.cpp src/face_model.cpp
            src/volume.cpp src/avatar_scale.cpp)
if(ESP_PLATFORM)
    idf_component_register(SRCS ${sources} INCLUDE_DIRS include)
    set(core_target ${COMPONENT_LIB})
else()
    add_library(grokwatch_core STATIC ${sources})
    target_include_directories(grokwatch_core PUBLIC include)
    set(core_target grokwatch_core)
endif()
target_compile_features(${core_target} PUBLIC cxx_std_17)
target_compile_options(${core_target} PRIVATE -Wall -Wextra -Werror -fno-exceptions -fno-rtti)
