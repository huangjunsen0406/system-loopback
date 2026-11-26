cmake_minimum_required(VERSION 3.18)
project(system_loopback VERSION 0.1.0 LANGUAGES C CXX)

option(SLB_BUILD_SHARED "Build shared library" ON)
option(SLB_BUILD_STATIC "Build static library" OFF)
option(SLB_BUILD_TESTS "Build C ABI unit tests" ON)

if(APPLE)
    enable_language(OBJC)
    set(SLB_SOURCES src/macos_tap.m)
elseif(WIN32)
    set(SLB_SOURCES src/windows_wasapi.cpp)
elseif(UNIX)
    set(SLB_SOURCES src/linux_pulse.c)
else()
    message(FATAL_ERROR "Unsupported platform")
endif()

function(slb_configure_target target_name is_shared)
    target_include_directories(${target_name}
        PUBLIC
            $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
            $<INSTALL_INTERFACE:include>
        PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/src
    )
    if(is_shared)
        target_compile_definitions(${target_name} PRIVATE SLB_EXPORTS)
    else()
        target_compile_definitions(${target_name} PUBLIC SLB_STATIC)
    endif()

    if(APPLE)
        target_compile_options(${target_name} PRIVATE
            -fobjc-arc -fvisibility=hidden -Wall -Wextra -mmacosx-version-min=11.0
        )
        target_link_libraries(${target_name} PRIVATE
            "-framework CoreAudio"
            "-framework Foundation"
            "-framework AudioToolbox"
        )
        if(is_shared)
            set_target_properties(${target_name} PROPERTIES
                INSTALL_NAME_DIR "@rpath"
                BUILD_WITH_INSTALL_RPATH ON
            )
        endif()
    elseif(WIN32)
        target_compile_features(${target_name} PRIVATE cxx_std_17)
        if(MSVC)
            target_compile_options(${target_name} PRIVATE /W3 /EHsc)
        endif()
        target_link_libraries(${target_name} PRIVATE ole32 avrt uuid)
    else()
        target_compile_options(${target_name} PRIVATE -fvisibility=hidden -Wall -Wextra)
        target_link_libraries(${target_name} PRIVATE dl pthread)
    endif()
endfunction()

if(SLB_BUILD_SHARED)
    add_library(system_loopback SHARED ${SLB_SOURCES})
    slb_configure_target(system_loopback TRUE)
    set_target_properties(system_loopback PROPERTIES OUTPUT_NAME "system_loopback")
endif()

if(SLB_BUILD_STATIC)
    add_library(system_loopback_static STATIC ${SLB_SOURCES})
    slb_configure_target(system_loopback_static FALSE)
endif()

if(SLB_BUILD_TESTS AND SLB_BUILD_SHARED)
    enable_testing()
    add_executable(test_abi tests/test_abi.c)
    target_include_directories(test_abi PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${CMAKE_CURRENT_SOURCE_DIR}/src
    )
    if(MSVC)
        target_compile_options(test_abi PRIVATE /std:c11 /experimental:c11atomics)
    else()
        set_target_properties(test_abi PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
        target_link_libraries(test_abi PRIVATE m)
    endif()
    target_link_libraries(test_abi PRIVATE system_loopback)
    add_test(NAME test_abi COMMAND test_abi)
endif()

include(GNUInstallDirs)
if(SLB_BUILD_SHARED)
    install(TARGETS system_loopback
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
        LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    )
endif()
install(FILES include/system_loopback.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
