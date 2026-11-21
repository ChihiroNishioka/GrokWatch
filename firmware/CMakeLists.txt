cmake_minimum_required(VERSION 3.16)

if(NOT DEFINED SDKCONFIG_DEFAULTS AND "$ENV{SDKCONFIG_DEFAULTS}" STREQUAL "")
    set(SDKCONFIG_DEFAULTS sdkconfig.defaults)
    if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/sdkconfig.local.defaults")
        list(APPEND SDKCONFIG_DEFAULTS sdkconfig.local.defaults)
    endif()
endif()

set(PROJECT_VER "0.1.0")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(grokwatch)
