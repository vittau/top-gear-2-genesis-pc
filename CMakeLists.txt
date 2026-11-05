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
find_package(SDL2 REQUIRED)
include("${RECOMP_ROOT}/cmake/GenesisRecompGenerated.cmake")
# The engine helper resolves ROM names relative to game/. Keep the private
# input outside the checkout, with no ROM staging or copying.
file(RELATIVE_PATH TG2_ROM_REL "${CMAKE_SOURCE_DIR}/game" "${TG2_ROM}")
genesisrecomp_add_generated_sources(GENERATED tg2 "${CMAKE_SOURCE_DIR}/game" "${TG2_ROM_REL}"
    REVERSE_DEBUG "${SONIC_REVERSE_DEBUG}")
genesisrecomp_runner_sources(RUNNER TRACE "${GEN_ENABLE_TRACE}" REVERSE_DEBUG "${SONIC_REVERSE_DEBUG}")
add_executable(TG2Recomp ${RUNNER} ${GENERATED} game/tg2_spec.c)
add_dependencies(TG2Recomp ${GENERATED_TARGET})
target_include_directories(TG2Recomp PRIVATE
    "${RUNNER_ROOT}" "${RUNNER_ROOT}/include" "${RUNNER_ROOT}/video"
    "${RUNNER_ROOT}/external/ymfm/src" "${RUNNER_ROOT}/external/superzazu"
    "${RUNNER_ROOT}/external/clowncommon" "${RECOMP_ROOT}/recompiler/src" game)
target_compile_definitions(TG2Recomp PRIVATE INCLUDE_GENERATED_CODE=1 ENABLE_RECOMPILED_CODE=1
    DEFAULT_DEBUG_PORT=4400
    $<$<BOOL:${GEN_ENABLE_TRACE}>:GEN_ENABLE_TRACE=1>
    $<$<BOOL:${SONIC_REVERSE_DEBUG}>:SONIC_REVERSE_DEBUG=1>)
target_link_libraries(TG2Recomp PRIVATE SDL2::SDL2main SDL2::SDL2)
genesisrecomp_runner_target(TG2Recomp)
include("${CMAKE_SOURCE_DIR}/recomp-ui/recomp_ui.cmake")
recomp_target_launcher_ui(TG2Recomp CONSOLE genesis)
