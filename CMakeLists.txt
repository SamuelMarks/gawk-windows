# =============================================================================
# CMakeLists.txt - GNU Awk Native Windows (MSVC) & OpenWatcom 32-bit DOS Build
#
# Orchestrates locating or fetching upstream gawk (5.4.60), build-time header
# and DOS compatibility shim generation (config.h, forwarding headers,
# gawk_dos_compat.c), C99-to-C89 AST source transformation via auto-win-msvc,
# POSIX/BSD/Linux polyfill linking, CPack installer packaging (ZIP, NSIS, WiX),
# and CTest functional verification.
#
# Parameters / Cache Variables:
#   GAWK_SOURCE_DIR                       - Path to upstream gawk source tree.
#   FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC - Path to local auto-win-msvc tree.
#   GAWK_BUILD_EXTENSIONS                 - Builds dynamic extensions (.dll).
#   BUILD_TESTING                         - Enables CTest functional tests.
# =============================================================================

cmake_minimum_required(VERSION 3.24)

if(CMAKE_SYSTEM_NAME STREQUAL "DOS" AND NOT CMAKE_SYSTEM_PROCESSOR STREQUAL "I86")
    if(NOT DEFINED CMAKE_SYSTEM_PROCESSOR OR CMAKE_SYSTEM_PROCESSOR STREQUAL "")
        set(CMAKE_SYSTEM_PROCESSOR "I386")
    endif()
    if(NOT DEFINED CMAKE_C_COMPILER)
        find_program(_gawk_wcl386 NAMES wcl386)
        if(_gawk_wcl386)
            set(CMAKE_C_COMPILER "${_gawk_wcl386}")
        endif()
    endif()
endif()

project(
    gawk-windows
    VERSION 5.4.60
    DESCRIPTION "GNU Awk pattern scanning and processing language for native Windows (MSVC) and 32-bit DOS (OpenWatcom)."
    HOMEPAGE_URL "https://www.gnu.org/software/gawk/"
    LANGUAGES C
)

include(FetchContent)
include(CTest)

if(CMAKE_SYSTEM_NAME STREQUAL "DOS" AND CMAKE_SYSTEM_PROCESSOR STREQUAL "I86")
    message(STATUS "Skipping 32-bit Protected-Mode gawk build on 16-bit Real Mode DOS (I86)")
    if(BUILD_TESTING)
        set(_i86_stub "${CMAKE_CURRENT_BINARY_DIR}/gawk_i86_skip.c")
        file(WRITE "${_i86_stub}" "int main(void) { return 0; }\n")
        add_executable(gawk_i86_skip)
        target_sources(gawk_i86_skip PRIVATE "${_i86_stub}")
        add_test(NAME gawk_i86_skip COMMAND gawk_i86_skip)
    endif()
    return()
endif()

include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/GenerateGawkHeaders.cmake")

if(CMAKE_SYSTEM_NAME STREQUAL "DOS" OR (CMAKE_C_COMPILER_ID MATCHES "Watcom" AND NOT WIN32))
    set(GAWK_TARGET_DOS TRUE)
else()
    set(GAWK_TARGET_DOS FALSE)
endif()

# -----------------------------------------------------------------------------
# 1. Load auto-win-msvc Compatibility Layer
# -----------------------------------------------------------------------------
if(NOT FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/auto-win-msvc/CMakeLists.txt")
        get_filename_component(_awm_dir "${CMAKE_CURRENT_SOURCE_DIR}/auto-win-msvc" ABSOLUTE)
        set(FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC "${_awm_dir}" CACHE PATH "Path to local auto-win-msvc source tree")
    elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../auto-win-msvc/CMakeLists.txt")
        get_filename_component(_awm_dir "${CMAKE_CURRENT_SOURCE_DIR}/../auto-win-msvc" ABSOLUTE)
        set(FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC "${_awm_dir}" CACHE PATH "Path to local auto-win-msvc source tree")
    endif()
endif()

if(DEFINED BUILD_SHARED_LIBS)
    set(_gawk_had_build_shared_libs TRUE)
    set(_gawk_saved_build_shared_libs "${BUILD_SHARED_LIBS}")
else()
    set(_gawk_had_build_shared_libs FALSE)
endif()
set(_gawk_saved_build_testing "${BUILD_TESTING}")
set(BUILD_SHARED_LIBS OFF)
set(BUILD_TESTING OFF)
set(AUTO_WIN_MSVC_BUILD_TESTING OFF)
if(GAWK_TARGET_DOS)
    set(AUTO_WIN_MSVC_SINGLE_THREADED ON)
endif()

FetchContent_Declare(
    auto_win_msvc
    GIT_REPOSITORY             https://github.com/SamuelMarks/auto-win-msvc.git
    GIT_TAG                    master
    GIT_REMOTE_UPDATE_STRATEGY CHECKOUT
)
FetchContent_MakeAvailable(auto_win_msvc)

if(_gawk_had_build_shared_libs)
    set(BUILD_SHARED_LIBS "${_gawk_saved_build_shared_libs}")
    unset(_gawk_saved_build_shared_libs)
else()
    unset(BUILD_SHARED_LIBS)
endif()
unset(_gawk_had_build_shared_libs)
set(BUILD_TESTING "${_gawk_saved_build_testing}")
unset(_gawk_saved_build_testing)

if(GAWK_TARGET_DOS)
    if(TARGET auto-win-msvc)
        set_target_properties(auto-win-msvc PROPERTIES EXCLUDE_FROM_ALL TRUE)
    endif()
    set(GAWK_DOS_FWD_DIR "${CMAKE_CURRENT_BINARY_DIR}/dos_posix_fwd")
    file(MAKE_DIRECTORY "${GAWK_DOS_FWD_DIR}/sys" "${GAWK_DOS_FWD_DIR}/bsd")
    foreach(_hdr IN ITEMS
        posix-core/include/posix-core.h
        posix-time/include/posix-time.h
        posix-libgen/include/posix-libgen.h
        posix-stat/include/posix-stat.h
        posix-pthread/include/posix-pthread.h
        posix-stdint/include/posix-stdint.h
        posix-inttypes/include/posix-inttypes.h
        posix-stdbool/include/posix-stdbool.h
        posix-types/include/posix-types.h
        linux-getopt/include/linux-getopt.h
    )
        configure_file("${auto_win_msvc_SOURCE_DIR}/${_hdr}" "${GAWK_DOS_FWD_DIR}/" COPYONLY)
    endforeach()
    configure_file(
        "${auto_win_msvc_SOURCE_DIR}/bsd-string/include/bsd/string.h"
        "${GAWK_DOS_FWD_DIR}/bsd/string.h"
        COPYONLY
    )
    file(WRITE "${GAWK_DOS_FWD_DIR}/sys/time.h" [=[#include "posix-time.h"
]=])
    file(WRITE "${GAWK_DOS_FWD_DIR}/sys/param.h" [=[#ifndef MAXPATHLEN
#define MAXPATHLEN 260
#endif
]=])
    file(WRITE "${GAWK_DOS_FWD_DIR}/libgen.h" [=[#include "posix-libgen.h"
]=])

    add_library(gawk_dos_compat STATIC)
    target_sources(gawk_dos_compat PRIVATE
        "${auto_win_msvc_SOURCE_DIR}/posix-core/src/posix-core.c"
        "${auto_win_msvc_SOURCE_DIR}/posix-time/src/posix-time.c"
        "${auto_win_msvc_SOURCE_DIR}/posix-libgen/src/posix-libgen.c"
        "${auto_win_msvc_SOURCE_DIR}/posix-stat/src/posix-stat.c"
        "${auto_win_msvc_SOURCE_DIR}/posix-stdint/src/posix-stdint.c"
        "${auto_win_msvc_SOURCE_DIR}/posix-inttypes/src/posix-inttypes.c"
        "${auto_win_msvc_SOURCE_DIR}/posix-stdbool/src/posix-stdbool.c"
        "${auto_win_msvc_SOURCE_DIR}/posix-types/src/posix-types.c"
        "${auto_win_msvc_SOURCE_DIR}/bsd-string/src/bsd_string.c"
    )
    target_include_directories(gawk_dos_compat PUBLIC
        "${GAWK_DOS_FWD_DIR}"
        "${auto_win_msvc_SOURCE_DIR}/include"
    )
    target_compile_definitions(gawk_dos_compat
        PUBLIC
            ETIMEDOUT=60
            EWOULDBLOCK=18
            _SINGLE_THREAD=1
            _BOOL_DEFINED=1
        PRIVATE
            AUTO_WIN_MSVC_MEGA_LIBRARY=1
    )
    if(CMAKE_C_COMPILER_ID MATCHES "Watcom")
        target_compile_options(gawk_dos_compat PRIVATE -bt=dos -mf -3r -zq -d0)
    endif()
endif()

# -----------------------------------------------------------------------------
# 2. Upstream gawk Source Location Discovery
# -----------------------------------------------------------------------------
if(NOT DEFINED GAWK_SOURCE_DIR)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/gawk/awk.h")
        get_filename_component(GAWK_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/gawk" ABSOLUTE)
    elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../gawk/awk.h")
        get_filename_component(GAWK_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../gawk" ABSOLUTE)
    endif()
endif()

if(NOT DEFINED GAWK_SOURCE_DIR OR NOT EXISTS "${GAWK_SOURCE_DIR}/awk.h")
    set(GAWK_SOURCE_DIR "${CMAKE_CURRENT_BINARY_DIR}/_deps/gawk_upstream-src")
    gawk_ensure_source(DEST_DIR "${GAWK_SOURCE_DIR}")
endif()

# -----------------------------------------------------------------------------
# 3. Generate Build-Time Headers & DOS Compatibility Shims
# -----------------------------------------------------------------------------
set(GAWK_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/gawk_generated")
set(_gen_args
    GAWK_DIR "${GAWK_SOURCE_DIR}"
    OUT_DIR "${GAWK_GEN_DIR}"
)
if(GAWK_TARGET_DOS)
    list(APPEND _gen_args TARGET_DOS)
endif()
gawk_generate_build_files(${_gen_args})

# -----------------------------------------------------------------------------
# 4. Assemble GNU Awk Targets & Usage Requirements
# -----------------------------------------------------------------------------
add_library(gawk_common INTERFACE)

target_include_directories(gawk_common INTERFACE
    "${GAWK_GEN_DIR}"
    "${GAWK_SOURCE_DIR}"
    "${GAWK_SOURCE_DIR}/support"
    "${GAWK_SOURCE_DIR}/missing_d"
    "${auto_win_msvc_SOURCE_DIR}/include"
)

target_compile_definitions(gawk_common INTERFACE
    HAVE_CONFIG_H=1
)

if(CMAKE_C_COMPILER_ID MATCHES "Watcom")
    target_compile_options(gawk_common INTERFACE
        -bt=dos
        -mf
        -3r
        -zq
        -d0
        -za99
        -ze
        -aa
        "-fi=${GAWK_GEN_DIR}/config.h"
        "-fi=${GAWK_DOS_FWD_DIR}/posix-core.h"
    )
else()
    target_compile_features(gawk_common INTERFACE c_std_11)
    if(MSVC)
        target_compile_options(gawk_common INTERFACE
            /W0
            "/FI${GAWK_GEN_DIR}/config.h"
        )
    else()
        target_compile_options(gawk_common INTERFACE
            -w
            "SHELL:-include '${GAWK_GEN_DIR}/config.h'"
        )
    endif()
endif()

if(GAWK_TARGET_DOS)
    target_link_libraries(gawk_common INTERFACE gawk_dos_compat)
else()
    target_link_libraries(gawk_common INTERFACE auto-win-msvc)
endif()

set(_gawk_base_sources
    "${GAWK_SOURCE_DIR}/array.c"
    "${GAWK_SOURCE_DIR}/awkgram.c"
    "${GAWK_SOURCE_DIR}/awkmem.c"
    "${GAWK_SOURCE_DIR}/builtin.c"
    "${GAWK_SOURCE_DIR}/cint_array.c"
    "${GAWK_SOURCE_DIR}/command.c"
    "${GAWK_SOURCE_DIR}/debug.c"
    "${GAWK_SOURCE_DIR}/eval.c"
    "${GAWK_SOURCE_DIR}/ext.c"
    "${GAWK_SOURCE_DIR}/field.c"
    "${GAWK_SOURCE_DIR}/floatcomp.c"
    "${GAWK_SOURCE_DIR}/gawkapi.c"
    "${GAWK_SOURCE_DIR}/int_array.c"
    "${GAWK_SOURCE_DIR}/main.c"
    "${GAWK_SOURCE_DIR}/mpfr.c"
    "${GAWK_SOURCE_DIR}/msg.c"
    "${GAWK_SOURCE_DIR}/node.c"
    "${GAWK_SOURCE_DIR}/printf.c"
    "${GAWK_SOURCE_DIR}/profile.c"
    "${GAWK_SOURCE_DIR}/re.c"
    "${GAWK_SOURCE_DIR}/str_array.c"
    "${GAWK_SOURCE_DIR}/symbol.c"
    "${GAWK_SOURCE_DIR}/version.c"
    "${GAWK_SOURCE_DIR}/support/getopt.c"
    "${GAWK_SOURCE_DIR}/support/getopt1.c"
    "${GAWK_SOURCE_DIR}/support/random.c"
)

add_executable(gawk)
target_compile_definitions(gawk PRIVATE GAWK=1)
target_link_libraries(gawk PRIVATE gawk_common)

if(GAWK_TARGET_DOS)
    include("${auto_win_msvc_SOURCE_DIR}/cmake/AutoWinMsvcTransform.cmake")
    auto_win_msvc_transform_sources(
        OUTPUT_VAR _gawk_dos_sources
        SOURCES
            ${_gawk_base_sources}
            "${GAWK_SOURCE_DIR}/replace.c"
            "${GAWK_GEN_DIR}/gawk_dos_minrx.c"
            "${GAWK_GEN_DIR}/gawk_dos_io.c"
            "${GAWK_GEN_DIR}/gawk_dos_compat.c"
        INCLUDE_DIRS
            "${GAWK_GEN_DIR}"
            "${GAWK_SOURCE_DIR}"
            "${GAWK_SOURCE_DIR}/support"
            "${GAWK_SOURCE_DIR}/missing_d"
    )
    target_sources(gawk PRIVATE ${_gawk_dos_sources})
    if(CMAKE_C_COMPILER_ID MATCHES "Watcom")
        target_link_options(gawk PRIVATE
            "SHELL:option stack=524288"
            "$<$<CONFIG:Debug,RelWithDebInfo>:SHELL:option symfile>"
        )
    endif()
else()
    add_library(gawk_replace OBJECT)
    target_sources(gawk_replace PRIVATE "${GAWK_SOURCE_DIR}/replace.c")
    target_compile_definitions(gawk_replace PRIVATE GAWK=1 GAWK_IN_REPLACE_C=1)
    target_link_libraries(gawk_replace PRIVATE gawk_common)

    add_library(gawk_popen OBJECT)
    target_sources(gawk_popen PRIVATE "${GAWK_SOURCE_DIR}/pc/popen.c")
    target_compile_definitions(gawk_popen PRIVATE GAWK=1 popen=_popen pclose=_pclose)
    target_link_libraries(gawk_popen PRIVATE gawk_common)

    target_sources(gawk PRIVATE
        ${_gawk_base_sources}
        "${GAWK_SOURCE_DIR}/support/minrx.c"
        "${GAWK_SOURCE_DIR}/io.c"
        "${GAWK_SOURCE_DIR}/gawkmisc.c"
        $<TARGET_OBJECTS:gawk_replace>
        $<TARGET_OBJECTS:gawk_popen>
    )
    if(MSVC)
        target_link_options(gawk PRIVATE
            /ALTERNATENAME:popen=_popen
            /ALTERNATENAME:pclose=_pclose
        )
    endif()
    if(WIN32)
        target_link_libraries(gawk PRIVATE
            ws2_32
            kernel32
            user32
            advapi32
        )
    endif()
endif()

option(GAWK_BUILD_EXTENSIONS "Build GNU Awk dynamic extensions (.dll)" OFF)
if(GAWK_BUILD_EXTENSIONS AND NOT GAWK_TARGET_DOS)
    foreach(_ext IN ITEMS ordchr readfile revoutput revtwoway rwarray intdiv time fnmatch inplace)
        if(EXISTS "${GAWK_SOURCE_DIR}/extension/${_ext}.c")
            add_library(gawk_ext_${_ext} SHARED)
            target_sources(gawk_ext_${_ext} PRIVATE "${GAWK_SOURCE_DIR}/extension/${_ext}.c")
            set_target_properties(gawk_ext_${_ext} PROPERTIES
                OUTPUT_NAME "${_ext}"
                PREFIX ""
            )
            target_compile_definitions(gawk_ext_${_ext} PRIVATE
                HAVE_STRPTIME=1
                S_IREAD=0x0100
                S_IWRITE=0x0080
                mkstemp=gawk_ext_mkstemp
            )
            if(MSVC)
                target_link_options(gawk_ext_${_ext} PRIVATE
                    /EXPORT:dl_load
                    /EXPORT:plugin_is_GPL_compatible
                )
            endif()
            target_link_libraries(gawk_ext_${_ext} PRIVATE gawk_common)
            install(TARGETS gawk_ext_${_ext} RUNTIME DESTINATION bin LIBRARY DESTINATION lib)
        endif()
    endforeach()
endif()

# -----------------------------------------------------------------------------
# 5. Install Rules & CPack Configuration
# -----------------------------------------------------------------------------
install(TARGETS gawk RUNTIME DESTINATION bin)
if(GAWK_TARGET_DOS AND DEFINED ENV{WATCOM})
    foreach(_dos_extender IN ITEMS dos32a.exe dos4gw.exe)
        if(EXISTS "$ENV{WATCOM}/binw/${_dos_extender}")
            install(FILES "$ENV{WATCOM}/binw/${_dos_extender}" DESTINATION bin)
        endif()
    endforeach()
endif()
foreach(_doc_file IN ITEMS README.md LICENSE-APACHE LICENSE-MIT LICENSE-CC0)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${_doc_file}")
        install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/${_doc_file}" DESTINATION .)
    endif()
endforeach()

include("${CMAKE_CURRENT_SOURCE_DIR}/CPackConfig.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/CPackSourceConfig.cmake")
include(CPack)

# -----------------------------------------------------------------------------
# 6. CTest Functional Verification Suite
# -----------------------------------------------------------------------------
if(BUILD_TESTING)
    if(GAWK_TARGET_DOS)
        add_test(
            NAME gawk_dos_suite
            COMMAND gawk "BEGIN{n=split(9.5,b,/[.]/);a[RS]=42;print(a[RS]);if((n!=2)+(b[1]/2!=4.5))exit(1)}"
        )
    else()
        add_test(NAME gawk_version COMMAND gawk --version)
        add_test(NAME gawk_begin_print COMMAND gawk [=[BEGIN { print "hello gawk" }]=])
        add_test(NAME gawk_math_arith COMMAND gawk [=[BEGIN { printf "%.2f\n", (10 + 20) / 4 }]=])
        add_test(NAME gawk_regex_match COMMAND gawk [=[BEGIN { if ("abc123xyz" ~ /[0-9]+/) exit 0; else exit 1 }]=])
        add_test(NAME gawk_field_split COMMAND gawk [=[BEGIN { n = split("a:b:c", arr, ":"); if (n == 3 && arr[2] == "b") print "ok"; else exit 1 }]=])
        add_test(NAME gawk_assoc_array COMMAND gawk [=[BEGIN { a["x"] = 42; a["y"] = 58; if (a["x"] + a["y"] == 100) exit 0; else exit 1 }]=])
    endif()
endif()
