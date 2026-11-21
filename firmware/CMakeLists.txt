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

# M5GFX 0.2.30 probes NVS before detecting the board, even if NVS was never initialized.
# Disable its board cache on a generated copy so the managed component stays intact.
idf_component_get_property(m5gfx_lib m5stack__m5gfx COMPONENT_LIB)
idf_component_get_property(m5gfx_dir m5stack__m5gfx COMPONENT_DIR)
set(m5gfx_source "${m5gfx_dir}/src/M5GFX.cpp")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${m5gfx_source}")
file(READ "${m5gfx_source}" m5gfx_original)
function(remove_m5gfx_cache_block input first next replacement output)
    string(FIND "${input}" "${first}" start)
    string(FIND "${input}" "${next}" end)
    if(start LESS 0 OR end LESS_EQUAL start)
        message(FATAL_ERROR "M5GFX board cache layout changed")
    endif()
    string(SUBSTRING "${input}" 0 ${start} before)
    string(SUBSTRING "${input}" ${end} -1 after)
    set(${output} "${before}${replacement}${after}" PARENT_SCOPE)
endfunction()

remove_m5gfx_cache_block("${m5gfx_original}" "    static constexpr char NVS_KEY"
    "    if (0 == nvs_board)" "    std::uint32_t nvs_board = 0;\n" m5gfx_patched)
remove_m5gfx_cache_block("${m5gfx_patched}" "    if (nvs_board != board) {" "    /// autodetect"
    "" m5gfx_patched)
if(m5gfx_patched MATCHES "nvs_[a-zA-Z0-9_]+[ 	]*[(]")
    message(FATAL_ERROR "M5GFX still contains NVS calls")
endif()

set(m5gfx_generated "${CMAKE_CURRENT_BINARY_DIR}/M5GFX.cpp")
file(GENERATE OUTPUT "${m5gfx_generated}" CONTENT "${m5gfx_patched}")
get_target_property(m5gfx_sources ${m5gfx_lib} SOURCES)
if(NOT m5gfx_source IN_LIST m5gfx_sources)
    message(FATAL_ERROR "M5GFX source list changed")
endif()
list(REMOVE_ITEM m5gfx_sources "${m5gfx_source}")
set_property(TARGET ${m5gfx_lib} PROPERTY SOURCES "${m5gfx_sources};${m5gfx_generated}")
