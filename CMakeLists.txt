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
#   BUILD_TESTING                         - Enables CTest functional tests.
# =============================================================================

cmake_minimum_required(VERSION 3.24)
cmake_policy(SET CMP0135 NEW)
set(CMAKE_POLICY_VERSION_MINIMUM 3.5)

project(gawk-windows VERSION 5.4.60 LANGUAGES C)

set(GAWK_VERSION "5.4.60")

include(FetchContent)
include(CTest)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

if(CMAKE_SYSTEM_NAME STREQUAL "DOS" OR (CMAKE_C_COMPILER_ID MATCHES "Watcom" AND NOT WIN32))
    set(AUTO_WIN_MSVC_SINGLE_THREADED ON CACHE BOOL "Single-threaded DOS mode" FORCE)
    set(GAWK_TARGET_DOS TRUE)
else()
    set(GAWK_TARGET_DOS FALSE)
endif()

set(_saved_build_shared_libs "${BUILD_SHARED_LIBS}")
set(_saved_build_testing "${BUILD_TESTING}")
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF)
set(AUTO_WIN_MSVC_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(AUTO_WIN_MSVC_BUILD_TESTING OFF)

# -----------------------------------------------------------------------------
# 1. Load auto-win-msvc Compatibility Layer
# -----------------------------------------------------------------------------
if(NOT DEFINED FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/auto-win-msvc/CMakeLists.txt")
        get_filename_component(_awm_dir "${CMAKE_CURRENT_SOURCE_DIR}/auto-win-msvc" ABSOLUTE)
        set(FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC "${_awm_dir}" CACHE PATH "" FORCE)
    elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../auto-win-msvc/CMakeLists.txt")
        get_filename_component(_awm_dir "${CMAKE_CURRENT_SOURCE_DIR}/../auto-win-msvc" ABSOLUTE)
        set(FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC "${_awm_dir}" CACHE PATH "" FORCE)
    endif()
endif()
if(DEFINED FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC AND NOT DEFINED FETCHCONTENT_SOURCE_DIR_AUTO-WIN-MSVC)
    set(FETCHCONTENT_SOURCE_DIR_AUTO-WIN-MSVC "${FETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC}" CACHE PATH "" FORCE)
endif()

if(GAWK_TARGET_DOS)
    add_compile_definitions(ETIMEDOUT=60 EWOULDBLOCK=18)
endif()

FetchContent_Declare(
    auto_win_msvc
    GIT_REPOSITORY https://github.com/SamuelMarks/auto-win-msvc.git
    GIT_TAG        e12ccc1e1657eb8d230d7c9d0e9d5ae4f8072326
)
FetchContent_MakeAvailable(auto_win_msvc)

if(GAWK_TARGET_DOS)
    if(TARGET auto-win-msvc)
        set_target_properties(auto-win-msvc PROPERTIES EXCLUDE_FROM_ALL TRUE)
    endif()
    set(GAWK_DOS_FWD_DIR "${CMAKE_CURRENT_BINARY_DIR}/dos_posix_fwd")
    file(MAKE_DIRECTORY "${GAWK_DOS_FWD_DIR}/sys" "${GAWK_DOS_FWD_DIR}/bsd")
    foreach(_hdr
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
    file(WRITE "${GAWK_DOS_FWD_DIR}/sys/time.h" "#include \"posix-time.h\"\n")
    file(WRITE "${GAWK_DOS_FWD_DIR}/sys/param.h" "#ifndef MAXPATHLEN\n#define MAXPATHLEN 260\n#endif\n")
    file(WRITE "${GAWK_DOS_FWD_DIR}/libgen.h" "#include \"posix-libgen.h\"\n")
    add_library(gawk_dos_compat STATIC
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
    target_compile_definitions(gawk_dos_compat PRIVATE
        _SINGLE_THREAD=1
        AUTO_WIN_MSVC_MEGA_LIBRARY=1
    )
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
    FetchContent_Declare(
        gawk_upstream
        URL https://ftp.gnu.org/gnu/gawk/gawk-5.3.1.tar.xz
    )
    FetchContent_MakeAvailable(gawk_upstream)
    set(GAWK_SOURCE_DIR "${gawk_upstream_SOURCE_DIR}")
endif()

set(BUILD_SHARED_LIBS "${_saved_build_shared_libs}")
set(BUILD_TESTING "${_saved_build_testing}" CACHE BOOL "" FORCE)
set(BUILD_TESTING "${_saved_build_testing}")

# -----------------------------------------------------------------------------
# 3. Generate Build-Time Headers & DOS Compatibility Shims
# -----------------------------------------------------------------------------
set(GAWK_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/gawk_generated")
file(MAKE_DIRECTORY "${GAWK_GEN_DIR}")

set(_gen_args
    "--gawk-dir" "${GAWK_SOURCE_DIR}"
    "--out-dir" "${GAWK_GEN_DIR}"
)
if(GAWK_TARGET_DOS)
    list(APPEND _gen_args "--dos")
endif()

execute_process(
    COMMAND "${Python3_EXECUTABLE}" -m scripts.generate_gawk_headers ${_gen_args}
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    RESULT_VARIABLE _gen_rc
)
if(NOT _gen_rc EQUAL 0)
    message(FATAL_ERROR "Failed to generate gawk headers via scripts/generate_gawk_headers.py")
endif()

# -----------------------------------------------------------------------------
# 4. Assemble GNU Awk Sources & Compile Target
# -----------------------------------------------------------------------------
set(GAWK_CORE_SOURCES
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
    "${GAWK_SOURCE_DIR}/replace.c"
    "${GAWK_SOURCE_DIR}/str_array.c"
    "${GAWK_SOURCE_DIR}/symbol.c"
    "${GAWK_SOURCE_DIR}/version.c"
    "${GAWK_SOURCE_DIR}/support/getopt.c"
    "${GAWK_SOURCE_DIR}/support/getopt1.c"
    "${GAWK_SOURCE_DIR}/support/minrx.c"
    "${GAWK_SOURCE_DIR}/support/random.c"
)

if(GAWK_TARGET_DOS)
    list(APPEND GAWK_CORE_SOURCES
        "${GAWK_GEN_DIR}/gawk_dos_io.c"
        "${GAWK_GEN_DIR}/gawk_dos_compat.c"
    )
    include("${auto_win_msvc_SOURCE_DIR}/cmake/AutoWinMsvcTransform.cmake")
    auto_win_msvc_transform_sources(
        OUTPUT_VAR GAWK_FINAL_SOURCES
        SOURCES ${GAWK_CORE_SOURCES}
        INCLUDE_DIRS
            "${GAWK_GEN_DIR}"
            "${GAWK_SOURCE_DIR}"
            "${GAWK_SOURCE_DIR}/support"
            "${GAWK_SOURCE_DIR}/missing_d"
    )
else()
    list(APPEND GAWK_CORE_SOURCES
        "${GAWK_SOURCE_DIR}/io.c"
        "${GAWK_SOURCE_DIR}/gawkmisc.c"
        "${GAWK_SOURCE_DIR}/pc/popen.c"
    )
    set_source_files_properties(
        "${GAWK_SOURCE_DIR}/pc/popen.c"
        PROPERTIES COMPILE_DEFINITIONS "popen=_popen;pclose=_pclose"
    )
    set_source_files_properties(
        "${GAWK_SOURCE_DIR}/replace.c"
        PROPERTIES COMPILE_DEFINITIONS "GAWK_IN_REPLACE_C=1"
    )
    set(GAWK_FINAL_SOURCES ${GAWK_CORE_SOURCES})
endif()

add_executable(gawk ${GAWK_FINAL_SOURCES})

if(CMAKE_C_COMPILER_ID MATCHES "Watcom")
    target_compile_options(gawk PRIVATE
        -za99
        -ze
        -aa
        -fi=${GAWK_GEN_DIR}/config.h
        -fi=${GAWK_DOS_FWD_DIR}/posix-core.h
    )
    target_link_options(gawk PRIVATE option stack=524288)
elseif(MSVC)
    target_compile_options(gawk PRIVATE
        /std:c11
        /W0
        /FI${GAWK_GEN_DIR}/config.h
    )
    target_link_options(gawk PRIVATE
        /ALTERNATENAME:popen=_popen
        /ALTERNATENAME:pclose=_pclose
    )
else()
    set_target_properties(gawk PROPERTIES C_STANDARD 11 C_EXTENSIONS ON)
    target_compile_options(gawk PRIVATE -w -include "${GAWK_GEN_DIR}/config.h")
endif()

target_include_directories(gawk PRIVATE
    "${GAWK_GEN_DIR}"
    "${GAWK_SOURCE_DIR}"
    "${GAWK_SOURCE_DIR}/support"
    "${GAWK_SOURCE_DIR}/missing_d"
    "${auto_win_msvc_SOURCE_DIR}/include"
)

target_compile_definitions(gawk PRIVATE
    GAWK=1
    HAVE_CONFIG_H=1
)

if(GAWK_TARGET_DOS)
    target_compile_definitions(gawk PRIVATE
        _SINGLE_THREAD=1
    )
    target_link_libraries(gawk PRIVATE
        gawk_dos_compat
    )
else()
    target_link_libraries(gawk PRIVATE
        auto-win-msvc
    )
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
    foreach(_ext ordchr readfile revoutput revtwoway rwarray intdiv time fnmatch inplace)
        if(EXISTS "${GAWK_SOURCE_DIR}/extension/${_ext}.c")
            add_library(gawk_ext_${_ext} SHARED "${GAWK_SOURCE_DIR}/extension/${_ext}.c")
            set_target_properties(gawk_ext_${_ext} PROPERTIES
                OUTPUT_NAME "${_ext}"
                PREFIX ""
            )
            target_include_directories(gawk_ext_${_ext} PRIVATE
                "${GAWK_GEN_DIR}"
                "${GAWK_SOURCE_DIR}"
                "${GAWK_SOURCE_DIR}/support"
                "${GAWK_SOURCE_DIR}/missing_d"
                "${auto_win_msvc_SOURCE_DIR}/include"
            )
            target_compile_definitions(gawk_ext_${_ext} PRIVATE HAVE_CONFIG_H=1 HAVE_STRPTIME=1 S_IREAD=0x0100 S_IWRITE=0x0080 mkstemp=gawk_ext_mkstemp)
            if(MSVC)
                target_compile_options(gawk_ext_${_ext} PRIVATE /std:c11 /W0 /FI${GAWK_GEN_DIR}/config.h)
                target_link_options(gawk_ext_${_ext} PRIVATE /EXPORT:dl_load /EXPORT:plugin_is_GPL_compatible)
            endif()
            target_link_libraries(gawk_ext_${_ext} PRIVATE auto-win-msvc)
            install(TARGETS gawk_ext_${_ext} RUNTIME DESTINATION bin LIBRARY DESTINATION lib)
        endif()
    endforeach()
endif()

# -----------------------------------------------------------------------------
# 5. Install Rules & CPack Configuration
# -----------------------------------------------------------------------------
install(TARGETS gawk RUNTIME DESTINATION bin)
if(GAWK_TARGET_DOS AND DEFINED ENV{WATCOM})
    if(EXISTS "$ENV{WATCOM}/binw/dos32a.exe")
        install(FILES "$ENV{WATCOM}/binw/dos32a.exe" DESTINATION bin)
    endif()
    if(EXISTS "$ENV{WATCOM}/binw/dos4gw.exe")
        install(FILES "$ENV{WATCOM}/binw/dos4gw.exe" DESTINATION bin)
    endif()
endif()
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/README.md")
    install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/README.md" DESTINATION .)
endif()
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-APACHE")
    install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-APACHE" DESTINATION .)
endif()
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-MIT")
    install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-MIT" DESTINATION .)
endif()
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-CC0")
    install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-CC0" DESTINATION .)
endif()

include("${CMAKE_CURRENT_SOURCE_DIR}/CPackConfig.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/CPackSourceConfig.cmake")
include(CPack)

# -----------------------------------------------------------------------------
# 6. CTest Functional Verification Suite
# -----------------------------------------------------------------------------
if(BUILD_TESTING)
    add_test(NAME gawk_version COMMAND gawk --version)
    add_test(NAME gawk_begin_print COMMAND gawk "BEGIN { print \"hello gawk\" }")
    add_test(NAME gawk_math_arith COMMAND gawk "BEGIN { printf \"%.2f\\n\", (10 + 20) / 4 }")
    add_test(NAME gawk_regex_match COMMAND gawk "BEGIN { if (\"abc123xyz\" ~ /[0-9]+/) exit 0; else exit 1 }")
    add_test(NAME gawk_field_split COMMAND gawk "BEGIN { n = split(\"a:b:c\", arr, \":\"); if (n == 3 && arr[2] == \"b\") print \"ok\"; else exit 1 }")
    add_test(NAME gawk_assoc_array COMMAND gawk "BEGIN { a[\"x\"] = 42; a[\"y\"] = 58; if (a[\"x\"] + a[\"y\"] == 100) exit 0; else exit 1 }")
endif()
