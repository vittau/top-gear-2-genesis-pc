cmake_minimum_required(VERSION 3.19)
project(TopGear2Recomp VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(GENESIS_RECOMP_ROOT "${CMAKE_SOURCE_DIR}/segagenesisrecomp" CACHE PATH "Genesis framework")
set(TG2_ROM "$ENV{HOME}/roms/genesis/tg2.bin" CACHE FILEPATH "Stock Top Gear 2 USA ROM")
set(RECOMP_ROOT "${GENESIS_RECOMP_ROOT}")
set(RUNNER_ROOT "${RECOMP_ROOT}/runner")
option(GEN_ENABLE_TRACE "TCP server and retrospective frame rings" ON)
option(SONIC_REVERSE_DEBUG "WRAM write and instruction history" ON)
# Development can use an installed SDL package. Release builders supply an
# SDL source checkout for static linkage and choose their target SDK/sysroot
# with CMAKE_TOOLCHAIN_FILE (not this workstation's libc).
set(TG2_SDL_SOURCE "" CACHE PATH "Optional SDL2 source checkout for bundled static builds")
if(TG2_SDL_SOURCE)
    set(SDL_SHARED OFF CACHE BOOL "" FORCE)
    set(SDL_STATIC ON CACHE BOOL "" FORCE)
    set(SDL_TEST OFF CACHE BOOL "" FORCE)
    add_subdirectory("${TG2_SDL_SOURCE}" "${CMAKE_BINARY_DIR}/sdl2" EXCLUDE_FROM_ALL)
elseif(WIN32)
    find_package(SDL2 REQUIRED CONFIG NO_DEFAULT_PATH
        PATHS "${RUNNER_ROOT}/external/SDL2/SDL2-2.28.5/cmake")
else()
    find_package(SDL2 REQUIRED CONFIG)
endif()
set(TG2_SDL_TARGET SDL2::SDL2)
if(TARGET SDL2::SDL2-static)
    set(TG2_SDL_TARGET SDL2::SDL2-static)
endif()
include("${RECOMP_ROOT}/cmake/GenesisRecompGenerated.cmake")
# The engine helper resolves ROM names relative to game/. Keep the private
# input outside the checkout, with no ROM staging or copying.
file(RELATIVE_PATH TG2_ROM_REL "${CMAKE_SOURCE_DIR}/game" "${TG2_ROM}")
genesisrecomp_add_generated_sources(GENERATED tg2 "${CMAKE_SOURCE_DIR}/game" "${TG2_ROM_REL}"
    REVERSE_DEBUG "${SONIC_REVERSE_DEBUG}")
genesisrecomp_runner_sources(RUNNER TRACE "${GEN_ENABLE_TRACE}" REVERSE_DEBUG "${SONIC_REVERSE_DEBUG}")
add_executable(TG2Recomp ${RUNNER} ${GENERATED} game/tg2_spec.c game/tg2_video.c game/tg2_options.c)
add_dependencies(TG2Recomp ${GENERATED_TARGET})
target_include_directories(TG2Recomp PRIVATE
    "${RUNNER_ROOT}" "${RUNNER_ROOT}/include" "${RUNNER_ROOT}/video"
    "${RUNNER_ROOT}/external/ymfm/src" "${RUNNER_ROOT}/external/superzazu"
    "${RUNNER_ROOT}/external/clowncommon" "${RECOMP_ROOT}/recompiler/src" game)
target_compile_definitions(TG2Recomp PRIVATE INCLUDE_GENERATED_CODE=1 ENABLE_RECOMPILED_CODE=1
    DEFAULT_DEBUG_PORT=4400
    $<$<BOOL:${GEN_ENABLE_TRACE}>:GEN_ENABLE_TRACE=1>
    $<$<BOOL:${SONIC_REVERSE_DEBUG}>:SONIC_REVERSE_DEBUG=1>)
target_link_libraries(TG2Recomp PRIVATE ${TG2_SDL_TARGET})
if(TARGET SDL2::SDL2main)
    target_link_libraries(TG2Recomp PRIVATE SDL2::SDL2main)
endif()
if(WIN32)
    target_link_libraries(TG2Recomp PRIVATE ws2_32 comdlg32)
    if(NOT TG2_SDL_SOURCE)
        add_custom_command(TARGET TG2Recomp POST_BUILD COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${RUNNER_ROOT}/external/SDL2/SDL2-2.28.5/lib/x64/SDL2.dll"
            "$<TARGET_FILE_DIR:TG2Recomp>" VERBATIM)
    endif()
endif()
genesisrecomp_runner_target(TG2Recomp)
# This game ships the built-in widescreen package in the launcher's Mods page.
set(RECOMP_UI_ENABLE_MODS ON)
include("${CMAKE_SOURCE_DIR}/recomp-ui/recomp_ui.cmake")
recomp_target_launcher_ui(TG2Recomp CONSOLE genesis)
