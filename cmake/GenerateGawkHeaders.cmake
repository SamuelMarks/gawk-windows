# =============================================================================
# cmake/GenerateGawkHeaders.cmake - CMake Build-Time Header & DOS Shim Codegen
#
# Replaces scripts/generate_gawk_headers.py with pure CMake functions for:
#   1. Fetching upstream GNU Awk (with shallow HTTPS fetch and multi-mirror
#      fallback).
#   2. Parsing AC_INIT(...) from upstream configure.ac.
#   3. Generating config.h and pc/ forwarding headers for Windows (MSVC/MinGW)
#      and 32-bit Protected-Mode DOS (OpenWatcom).
#   4. Generating DOS compatibility C translation units (gawk_dos_compat.c,
#      gawk_dos_minrx.c, gawk_dos_io.c).
# =============================================================================

set(GAWK_DEFAULT_REV "9b2156156f47076b5e588448a89129cc59701a65")
set(GAWK_DEFAULT_REPOS
    "https://https.git.savannah.gnu.org/git/gawk.git"
    "https://git.savannah.gnu.org/git/gawk.git"
    "git://git.savannah.gnu.org/gawk.git"
)

string(ASCII 92 _GAWK_BS)
string(ASCII 34 _GAWK_DQ)
string(ASCII 10 _GAWK_NL)
string(ASCII 9 _GAWK_TAB)

# -----------------------------------------------------------------------------
# gawk_ensure_source(
#   DEST_DIR <dir>
#   [COMMIT <sha>]
#   [REPO_URLS <url1> <url2> ...]
#   [RETRIES_PER_URL <n>]
#   [RETRY_DELAY_SEC <sec>]
# )
# -----------------------------------------------------------------------------
function(gawk_ensure_source)
    set(_options "")
    set(_one_value_args DEST_DIR COMMIT RETRIES_PER_URL RETRY_DELAY_SEC)
    set(_multi_value_args REPO_URLS)
    cmake_parse_arguments(ARG "${_options}" "${_one_value_args}" "${_multi_value_args}" ${ARGN})

    if(NOT ARG_DEST_DIR)
        message(FATAL_ERROR "gawk_ensure_source: DEST_DIR is required")
    endif()
    if(NOT ARG_COMMIT)
        set(ARG_COMMIT "${GAWK_DEFAULT_REV}")
    endif()
    if(NOT DEFINED ARG_REPO_URLS)
        set(ARG_REPO_URLS ${GAWK_DEFAULT_REPOS})
    endif()
    if(NOT DEFINED ARG_RETRIES_PER_URL)
        set(ARG_RETRIES_PER_URL 3)
    endif()
    if(NOT DEFINED ARG_RETRY_DELAY_SEC)
        set(ARG_RETRY_DELAY_SEC 2)
    endif()

    get_filename_component(_resolved "${ARG_DEST_DIR}" ABSOLUTE)
    if(EXISTS "${_resolved}/awk.h" AND EXISTS "${_resolved}/configure.ac")
        return()
    endif()

    set(_errors "")
    foreach(_url IN LISTS ARG_REPO_URLS)
        foreach(_attempt RANGE 1 ${ARG_RETRIES_PER_URL})
            if(EXISTS "${_resolved}")
                file(REMOVE_RECURSE "${_resolved}")
            endif()
            file(MAKE_DIRECTORY "${_resolved}")

            if(NOT _url MATCHES "^git://")
                execute_process(
                    COMMAND git init "${_resolved}"
                    RESULT_VARIABLE _init_rc
                    OUTPUT_VARIABLE _init_out
                    ERROR_VARIABLE _init_err
                    OUTPUT_STRIP_TRAILING_WHITESPACE
                    ERROR_STRIP_TRAILING_WHITESPACE
                )
                execute_process(
                    COMMAND git -C "${_resolved}"
                            -c http.lowSpeedLimit=1000
                            -c http.lowSpeedTime=30
                            fetch --depth 1 --no-tags "${_url}" "${ARG_COMMIT}"
                    RESULT_VARIABLE _fetch_rc
                    OUTPUT_VARIABLE _fetch_out
                    ERROR_VARIABLE _fetch_err
                    OUTPUT_STRIP_TRAILING_WHITESPACE
                    ERROR_STRIP_TRAILING_WHITESPACE
                )
                if(_init_rc EQUAL 0 AND _fetch_rc EQUAL 0)
                    execute_process(
                        COMMAND git -C "${_resolved}" checkout --force FETCH_HEAD
                        RESULT_VARIABLE _co_rc
                        OUTPUT_VARIABLE _co_out
                        ERROR_VARIABLE _co_err
                        OUTPUT_STRIP_TRAILING_WHITESPACE
                        ERROR_STRIP_TRAILING_WHITESPACE
                    )
                    if(_co_rc EQUAL 0 AND EXISTS "${_resolved}/awk.h")
                        return()
                    endif()
                    list(APPEND _errors "${_url} (shallow checkout attempt ${_attempt}): ${_co_err}")
                else()
                    list(APPEND _errors "${_url} (shallow fetch attempt ${_attempt}): ${_fetch_err}")
                endif()
            else()
                execute_process(
                    COMMAND git clone --no-checkout "${_url}" "${_resolved}"
                    RESULT_VARIABLE _clone_rc
                    OUTPUT_VARIABLE _clone_out
                    ERROR_VARIABLE _clone_err
                    OUTPUT_STRIP_TRAILING_WHITESPACE
                    ERROR_STRIP_TRAILING_WHITESPACE
                )
                if(_clone_rc EQUAL 0)
                    execute_process(
                        COMMAND git -C "${_resolved}" checkout --force "${ARG_COMMIT}"
                        RESULT_VARIABLE _co_rc
                        OUTPUT_VARIABLE _co_out
                        ERROR_VARIABLE _co_err
                        OUTPUT_STRIP_TRAILING_WHITESPACE
                        ERROR_STRIP_TRAILING_WHITESPACE
                    )
                    if(_co_rc EQUAL 0 AND EXISTS "${_resolved}/awk.h")
                        return()
                    endif()
                    list(APPEND _errors "${_url} (clone checkout attempt ${_attempt}): ${_co_err}")
                else()
                    list(APPEND _errors "${_url} (clone attempt ${_attempt}): ${_clone_err}")
                endif()
            endif()

            if(ARG_RETRY_DELAY_SEC GREATER 0)
                math(EXPR _sleep_sec "${ARG_RETRY_DELAY_SEC} * ${_attempt}")
                execute_process(COMMAND "${CMAKE_COMMAND}" -E sleep "${_sleep_sec}")
            endif()
        endforeach()
    endforeach()

    if(_errors)
        string(JOIN "; " _joined_errors ${_errors})
    else()
        set(_joined_errors "no repository URLs configured")
    endif()
    message(FATAL_ERROR "Failed to fetch upstream gawk (${ARG_COMMIT}): ${_joined_errors}")
endfunction()

# -----------------------------------------------------------------------------
# gawk_parse_ac_init(<configure_ac_text> <out_pkg_name> <out_version> <out_bugreport> <out_tarname>)
# -----------------------------------------------------------------------------
function(gawk_parse_ac_init CONFIGURE_AC_TEXT OUT_PKG_NAME OUT_VERSION OUT_BUGREPORT OUT_TARNAME)
    set(_pkg_name "GNU Awk")
    set(_version "5.4.60")
    set(_bugreport "bug-gawk@gnu.org")
    set(_tarname "gawk")

    set(_ac_re "AC_INIT${_GAWK_BS}(${_GAWK_BS}[?([^],]+)${_GAWK_BS}]?,[ ${_GAWK_TAB}]*${_GAWK_BS}[?([^],]+)${_GAWK_BS}]?,[ ${_GAWK_TAB}]*${_GAWK_BS}[?([^],]+)${_GAWK_BS}]?,[ ${_GAWK_TAB}]*${_GAWK_BS}[?([^],)]+)${_GAWK_BS}]?")
    string(REGEX MATCH "${_ac_re}" _ac_match "${CONFIGURE_AC_TEXT}")
    if(_ac_match)
        string(STRIP "${CMAKE_MATCH_1}" _pkg_name)
        string(STRIP "${CMAKE_MATCH_2}" _version)
        string(STRIP "${CMAKE_MATCH_3}" _bugreport)
        string(STRIP "${CMAKE_MATCH_4}" _tarname)
    endif()

    set(${OUT_PKG_NAME} "${_pkg_name}" PARENT_SCOPE)
    set(${OUT_VERSION} "${_version}" PARENT_SCOPE)
    set(${OUT_BUGREPORT} "${_bugreport}" PARENT_SCOPE)
    set(${OUT_TARNAME} "${_tarname}" PARENT_SCOPE)
endfunction()

# -----------------------------------------------------------------------------
# gawk_build_config_h(
#   PACKAGE_NAME <name>
#   VERSION <ver>
#   BUGREPORT <email>
#   TARNAME <tarname>
#   [TARGET_DOS]
#   OUTPUT_VAR <var>
# )
# -----------------------------------------------------------------------------
function(gawk_build_config_h)
    set(_options TARGET_DOS)
    set(_one_value_args PACKAGE_NAME VERSION BUGREPORT TARNAME OUTPUT_VAR)
    set(_multi_value_args "")
    cmake_parse_arguments(ARG "${_options}" "${_one_value_args}" "${_multi_value_args}" ${ARGN})

    set(_pkg_string "${ARG_PACKAGE_NAME} ${ARG_VERSION}")
    set(_pkg_url "http://www.gnu.org/software/gawk/")
    if(ARG_TARGET_DOS)
        set(_shlibext "dxe")
    else()
        set(_shlibext "dll")
    endif()

    set(_cfg_common [=[/* Generated config.h for GNU Awk via gawk-windows & auto-win-msvc */
#ifndef GAWK_AUTO_WIN_MSVC_CONFIG_H
#define GAWK_AUTO_WIN_MSVC_CONFIG_H

#define PACKAGE "@ARG_TARNAME@"
#define PACKAGE_NAME "@ARG_PACKAGE_NAME@"
#define PACKAGE_TARNAME "@ARG_TARNAME@"
#define PACKAGE_VERSION "@ARG_VERSION@"
#define VERSION "@ARG_VERSION@"
#define PACKAGE_STRING "@_pkg_string@"
#define PACKAGE_BUGREPORT "@ARG_BUGREPORT@"
#define PACKAGE_URL "@_pkg_url@"

#ifndef DEFPATH
#define DEFPATH "."
#endif
#ifndef DEFLIBPATH
#define DEFLIBPATH "."
#endif
#ifndef SHLIBEXT
#define SHLIBEXT "@_shlibext@"
#endif

#define _GNU_SOURCE 1
#define _CRT_SECURE_NO_WARNINGS 1
#define _CRT_NONSTDC_NO_DEPRECATE 1
#define _WINSOCK_DEPRECATED_NO_WARNINGS 1

#define STDC_HEADERS 1
#define PROTOTYPES 1
#define HAVE_STRINGIZE 1
#define HAVE_STDARG_H 1
#define HAVE_STDBOOL_H 1
#define HAVE_STDDEF_H 1
#define HAVE_STDINT_H 1
#define HAVE_STDIO_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRING_H 1
#define HAVE_STRINGS_H 1
#define HAVE_INTTYPES_H 1
#define HAVE_INTTYPES_H_WITH_UINTMAX 1
#define HAVE_LIMITS_H 1
#define HAVE_LOCALE_H 1
#define HAVE_MEMORY_H 1
#define HAVE_FCNTL_H 1
#define HAVE_SYS_STAT_H 1
#define HAVE_SYS_TYPES_H 1
#define HAVE_SYS_TIME_H 1
#define HAVE_SYS_PARAM_H 1
#define HAVE_UNISTD_H 1
#define HAVE_WCHAR_H 1
#define HAVE_WCTYPE_H 1
#define HAVE_WCTYPE 1
#define HAVE_WCTYPE_T 1
#define HAVE_WINT_T 1
#define HAVE_BTOWC 1
#define HAVE_ISWCTYPE 1
#define HAVE_ISWLOWER 1
#define HAVE_ISWUPPER 1
#define HAVE_TOWLOWER 1
#define HAVE_TOWUPPER 1
#define HAVE_MBRLEN 1
#define HAVE_MBRTOWC 1
#define HAVE_WCRTOMB 1
#define HAVE_WCSCOLL 1
#define HAVE_ATEXIT 1
#define HAVE_FMOD 1
#define HAVE_ISASCII 1
#define HAVE_ISBLANK 1
#define HAVE_INTMAX_T 1
#define HAVE_UINTMAX_T 1
#define HAVE_LONG_LONG 1
#define HAVE_LONG_LONG_INT 1
#define HAVE_UNSIGNED_LONG_LONG 1
#define HAVE_UNSIGNED_LONG_LONG_INT 1
#define HAVE_MEMCMP 1
#define HAVE_MEMCPY 1
#define HAVE_MEMMOVE 1
#define HAVE_MEMSET 1
#define HAVE_MKTIME 1
#define HAVE_SETENV 1
#define HAVE_SETLOCALE 1
#define HAVE_SNPRINTF 1
#define HAVE_STRCHR 1
#define HAVE_STRCOLL 1
#define HAVE_STRERROR 1
#define HAVE_STRCASECMP 1
#define HAVE_STRNCASECMP 1
#define HAVE_STRSIGNAL 1
#define HAVE_STRTOD 1
#define HAVE_STRTOUL 1
#define HAVE_SYSTEM 1
#undef HAVE_TIMEGM
#define HAVE_TZSET 1
#define HAVE_VPRINTF 1
#define HAVE_GETTIMEOFDAY 1
#define HAVE_LANGINFO_CODESET 1
#define GETPGRP_VOID 1
#define GETGROUPS_T int
#define RETSIGTYPE void
#define SIZEOF_UNSIGNED_INT 4
#define SIZEOF_UNSIGNED_LONG 4
#define TIME_WITH_SYS_TIME 1
#define HAVE_POPEN_H 1
#define strftime rpl_strftime

/* Disable optional POSIX/GNU features not applicable to standalone Windows/DOS */
#undef ENABLE_NLS
#undef HAVE_LIBINTL_H
#undef HAVE_LIBREADLINE
#undef HAVE_MPFR
#undef USE_PERSISTENT_MALLOC

]=])
    string(CONFIGURE "${_cfg_common}" _cfg @ONLY)

    if(ARG_TARGET_DOS)
        set(_cfg_dos [=[/* 32-bit Protected-Mode DOS (OpenWatcom / DJGPP) Configuration */
#undef DYNAMIC
#undef HAVE_SOCKETS
#undef HAVE_GETADDRINFO
#undef HAVE_UCHAR_H
#undef HAVE_MBRTOC32
#undef HAVE_C32RTOMB
#undef HAVE_USLEEP
#undef HAVE_TZNAME
#undef HAVE_DECL_TZNAME
#define PIPES_SIMULATED 1
#define HAVE_POPEN_H 1

#ifndef __STDC__
#define __STDC__ 1
#endif
#ifdef __WATCOMC__
#define __restrict__
#define restrict
#define inline __inline
#ifndef __attribute__
#define __attribute__(x)
#endif
#define _Noreturn
#endif

#ifndef SIGHUP
#define SIGHUP 1
#endif
#ifndef SIGQUIT
#define SIGQUIT 3
#endif
#ifndef SIGPIPE
#define SIGPIPE 13
#endif
#ifndef SIGKILL
#define SIGKILL 9
#endif
#ifndef WIFEXITED
#define WIFEXITED(w) (((w) & 0xff) == 0)
#endif
#ifndef WIFSIGNALED
#define WIFSIGNALED(w) (((w) & 0x7f) > 0 && (((w) & 0x7f) < 0x7f))
#endif
#ifndef WTERMSIG
#define WTERMSIG(w) ((w) & 0x7f)
#endif

#include <limits.h>
#include <stdbool.h>
#include <sys/stat.h>
#include <fcntl.h>
#if defined(S_IFSOCK) && S_IFSOCK == 0
#undef S_IFSOCK
#endif
#if defined(S_IFLNK) && S_IFLNK == 0
#undef S_IFLNK
#endif
#if defined(S_IFBLK) && S_IFBLK == 0
#undef S_IFBLK
#define S_IFBLK 0060000
#endif
#ifndef fd_set
typedef unsigned int fd_set;
#define FD_ZERO(set) (*(set) = 0)
#define FD_SET(fd, set) (*(set) |= (1U << ((fd) & 31)))
#define FD_ISSET(fd, set) ((*(set) & (1U << ((fd) & 31))) != 0)
#define select(nfds, rfds, wfds, efds, tv) (1)
#endif
int wait_any(int interesting);
int kill(int pid, int sig);
int pipe(int fds[2]);
int fork(void);
int wait(int *status);
#include "custom.h"

int getpgrp(void);
#endif /* GAWK_AUTO_WIN_MSVC_CONFIG_H */
]=])
        string(APPEND _cfg "${_cfg_dos}")
    else()
        set(_cfg_win [=[/* Native Windows (MSVC / clang-cl / MinGW) Configuration */
#define DYNAMIC 1
#define HAVE_SOCKETS 1
#define HAVE_SOCKADDR_STORAGE 1
#define HAVE_GETADDRINFO 1
#define HAVE_GAI_STRERROR 1
#define HAVE_USLEEP 1
#define HAVE_TZNAME 1
#define HAVE_DECL_TZNAME 1
#define PRINTF_HAS_A_FORMAT 1
#define PRINTF_HAS_F_FORMAT 1

#ifndef __MINGW32__
#define __MINGW32__ 1
#endif
#ifdef _UCRT
#undef _UCRT
#endif
#ifndef __STDC__
#define __STDC__ 1
#endif

#ifdef _MSC_VER
#define __MINGW32_MAJOR_VERSION 5
#define __restrict__ __restrict
#define restrict __restrict
#define inline __inline
#ifndef __attribute__
#define __attribute__(x)
#endif
#define _Noreturn __declspec(noreturn)
#include <BaseTsd.h>
#ifndef _SSIZE_T_DEFINED
#define _SSIZE_T_DEFINED
typedef SSIZE_T ssize_t;
#endif
#ifndef _MODE_T_DEFINED
#define _MODE_T_DEFINED
typedef unsigned short mode_t;
#endif
#ifndef _PID_T_DEFINED
#define _PID_T_DEFINED
typedef int pid_t;
#endif
#ifndef _USECONDS_T_DEFINED
#define _USECONDS_T_DEFINED
typedef unsigned int useconds_t;
#endif
#include <stdio.h>
#include <fcntl.h>
#include <process.h>
#include <time.h>
#ifndef O_NOINHERIT
#define O_NOINHERIT 0x0080
#endif
#ifndef P_WAIT
#define P_WAIT _P_WAIT
#endif
#ifndef P_NOWAIT
#define P_NOWAIT _P_NOWAIT
#endif
#ifndef tzname
#define tzname _tzname
#endif
#ifndef environ
#define environ _environ
#endif
#ifndef isascii
#define isascii __isascii
#endif
#define setenv gawk_w32_setenv
#define unsetenv gawk_w32_unsetenv
#define xmalloc malloc
#endif /* _MSC_VER */

#include <limits.h>
#include <stdbool.h>
#include <wchar.h>
#include <wctype.h>
#ifdef _UCRT
#undef _UCRT
#endif
#include "mbc32.h"
#define _UCRT 1
#include "custom.h"
#ifndef GAWK_IN_REPLACE_C
#undef _UCRT
#endif

#endif /* GAWK_AUTO_WIN_MSVC_CONFIG_H */
]=])
        string(APPEND _cfg "${_cfg_win}")
    endif()

    set(${ARG_OUTPUT_VAR} "${_cfg}" PARENT_SCOPE)
endfunction()

# -----------------------------------------------------------------------------
# gawk_build_dos_compat_c(<gawk_source_dir> <output_var>)
# -----------------------------------------------------------------------------
function(gawk_build_dos_compat_c GAWK_SOURCE_DIR OUTPUT_VAR)
    set(_popen_c_file "${GAWK_SOURCE_DIR}/pc/popen.c")
    set(_popen_c_body "")
    if(EXISTS "${_popen_c_file}")
        file(READ "${_popen_c_file}" _popen_c_body)
    endif()

    set(_src_tpl [=[/* Generated gawk_dos_compat.c for 32-bit Protected-Mode DOS (OpenWatcom) */
#include "awk.h"
#include <io.h>
#include <dos.h>
#include <direct.h>
#include <process.h>

const char quote = '@_GAWK_BS@'';
const char envsep = ';';
const char *defpath = DEFPATH;
const char *deflibpath = DEFLIBPATH;

#ifndef INVALID_HANDLE
#define INVALID_HANDLE (-1)
#endif

const char *
gawk_name(const char *filespec)
{
    char *p = (char *)filespec;
    char *q;
    if ((q = strrchr(p, '@_GAWK_BS@@_GAWK_BS@')) != NULL)
        p = q + 1;
    if ((q = strrchr(p, '/')) != NULL && (p == NULL || q > p))
        p = q + 1;
    if ((q = strchr(p, '.')) != NULL)
        *q = '@_GAWK_BS@0';
    return strlwr(p);
}

void
os_arg_fixup(int *argcp, char ***argvp)
{
    (void)argcp;
    (void)argvp;
}

int
os_devopen(const char *name, int flag)
{
    if (strcmp(name, "/dev/null") == 0)
        return open("NUL", flag);
    return INVALID_HANDLE;
}

size_t
optimal_bufsize(int fd, struct stat *stb)
{
    memset(stb, '@_GAWK_BS@0', sizeof(struct stat));
    if (fstat(fd, stb) == -1)
        fatal("can't stat fd %d (%s)", fd, strerror(errno));
    if (S_ISREG(stb->st_mode) && stb->st_size > 0 && stb->st_size < BUFSIZ)
        return (size_t)stb->st_size;
    return BUFSIZ;
}

int
ispath(const char *file)
{
    for (; *file; file++) {
        if (*file == '/' || *file == '@_GAWK_BS@@_GAWK_BS@' || *file == ':')
            return 1;
    }
    return 0;
}

int
isdirpunct(int c)
{
    return (c == ':' || c == '@_GAWK_BS@@_GAWK_BS@' || c == '/');
}

void
os_close_on_exec(int fd, const char *name, const char *what, const char *dir)
{
    (void)fd;
    (void)name;
    (void)what;
    (void)dir;
}

int
os_isdir(int fd)
{
    struct stat sbuf;
    return (fstat(fd, &sbuf) == 0 && S_ISDIR(sbuf.st_mode));
}

int
os_isreadable(const awk_input_buf_t *iobuf, bool *isdir)
{
    *isdir = false;
    if (iobuf->fd == INVALID_HANDLE)
        return false;
    switch (iobuf->sbuf.st_mode & S_IFMT) {
    case S_IFREG:
    case S_IFCHR:
        return true;
    case S_IFDIR:
        *isdir = true;
        return false;
    default:
        return false;
    }
}

int
os_is_setuid(void)
{
    return 0;
}

static int orig_tty_mode = -1;

int
os_setbinmode(int fd, int mode)
{
    int prev_mode = setmode(fd, mode);
    if (orig_tty_mode == -1 && fd >= 0 && fd <= 2)
        orig_tty_mode = prev_mode;
    return prev_mode;
}

void
os_restore_mode(int fd)
{
    if (orig_tty_mode != -1)
        setmode(fd, orig_tty_mode);
}

int
os_isatty(int fd)
{
    return isatty(fd);
}

int
files_are_same(char *path, SRCFILE *src)
{
    struct stat st;
    if (stat(path, &st) == 0) {
        return (st.st_dev == src->sbuf.st_dev
                && st.st_ino == src->sbuf.st_ino
                && st.st_mtime == src->mtime);
    }
    return 0;
}

void
init_sockets(void)
{
}

void
os_maybe_set_errno(void)
{
}

void
os_disable_aslr(const char *persist_file, char **argv)
{
    (void)persist_file;
    (void)argv;
}

char *
nl_langinfo(int item)
{
    (void)item;
    return "ASCII";
}

char *
strsignal(int signo)
{
    switch (signo) {
    case SIGINT: return "SIGINT";
    case SIGILL: return "SIGILL";
    case SIGFPE: return "SIGFPE";
    case SIGSEGV: return "SIGSEGV";
    case SIGTERM: return "SIGTERM";
    case SIGABRT: return "SIGABRT";
    default: return "Unknown signal";
    }
}

int
wait_any(int interesting)
{
    (void)interesting;
    errno = ECHILD;
    return -1;
}

int
wait(int *status)
{
    if (status)
        *status = 0;
    errno = ECHILD;
    return -1;
}

int
kill(int pid, int sig)
{
    (void)pid;
    (void)sig;
    errno = ENOSYS;
    return -1;
}

int
execl(const char *path, const char *arg0, ...)
{
    (void)path;
    (void)arg0;
    errno = ENOSYS;
    return -1;
}
]=])
    string(CONFIGURE "${_src_tpl}" _src_prefix @ONLY)
    string(CONCAT _src "${_src_prefix}" "${_popen_c_body}" "${_GAWK_NL}")
    set(${OUTPUT_VAR} "${_src}" PARENT_SCOPE)
endfunction()

# -----------------------------------------------------------------------------
# gawk_build_dos_minrx_c(<gawk_source_dir> <output_var>)
# -----------------------------------------------------------------------------
function(gawk_build_dos_minrx_c GAWK_SOURCE_DIR OUTPUT_VAR)
    set(_minrx_src "${GAWK_SOURCE_DIR}/support/minrx.c")
    set(_content "")
    if(EXISTS "${_minrx_src}")
        file(READ "${_minrx_src}" _content)
    endif()

    string(FIND "${_content}" "LITERAL(Subexp)" _has_literal)
    string(FIND "${_content}" "awm_make_Subexp(" _has_awm_make)
    if(NOT _has_literal EQUAL -1 AND _has_awm_make EQUAL -1)
        set(_qvec_old [=[struct QVecInsert {
	bool newly;
	NState *newnsp;
};]=])
        set(_qvec_new [=[struct QVecInsert {
	bool newly;
	NState *newnsp;
};
static __inline QVecInsert awm_make_QVecInsert(bool n, NState *p) { QVecInsert r; r.newly = n; r.newnsp = p; return r; }]=])
        string(REPLACE "${_qvec_old}" "${_qvec_new}" _content "${_content}")

        string(REPLACE
            "return LITERAL(QVecInsert) {newly, &q->storage[k]};"
            "return awm_make_QVecInsert(newly, &q->storage[k]);"
            _content
            "${_content}"
        )

        set(_subexp_old [=[struct Subexp {
	NodeList nodes;
	size_t maxstk;
	bool hasmin;
};]=])
        set(_subexp_new [=[struct Subexp {
	NodeList nodes;
	size_t maxstk;
	bool hasmin;
};
static __inline Subexp awm_make_Subexp(NodeList n, size_t m, bool h) { Subexp r; r.nodes = n; r.maxstk = m; r.hasmin = h; return r; }
static __inline Subexp awm_make_Subexp_empty(void) { Subexp r; r.nodes.first = NULL; r.nodes.final = NULL; r.nodes.size = 0; r.maxstk = 0; r.hasmin = false; return r; }]=])
        string(REPLACE "${_subexp_old}" "${_subexp_new}" _content "${_content}")

        string(REPLACE
            "LITERAL(Subexp) {{NULL, NULL, 0}, 0, false}"
            "awm_make_Subexp_empty()"
            _content
            "${_content}"
        )
        set(_subexp_re "LITERAL${_GAWK_BS}(Subexp${_GAWK_BS})[ ${_GAWK_TAB}]*${_GAWK_BS}{[ ${_GAWK_TAB}]*([^,{}]+)[ ${_GAWK_TAB}]*,[ ${_GAWK_TAB}]*([^,{}]+)[ ${_GAWK_TAB}]*,[ ${_GAWK_TAB}]*([^${_GAWK_TAB} {}]+)[ ${_GAWK_TAB}]*${_GAWK_BS}}")
        set(_subexp_rep "awm_make_Subexp(${_GAWK_BS}1, ${_GAWK_BS}2, ${_GAWK_BS}3)")
        string(REGEX REPLACE "${_subexp_re}" "${_subexp_rep}" _content "${_content}")
    endif()

    set(${OUTPUT_VAR} "${_content}" PARENT_SCOPE)
endfunction()

# -----------------------------------------------------------------------------
# gawk_generate_build_files(
#   GAWK_DIR <dir>
#   OUT_DIR <dir>
#   [TARGET_DOS]
# )
# -----------------------------------------------------------------------------
function(gawk_generate_build_files)
    set(_options TARGET_DOS)
    set(_one_value_args GAWK_DIR OUT_DIR)
    set(_multi_value_args "")
    cmake_parse_arguments(ARG "${_options}" "${_one_value_args}" "${_multi_value_args}" ${ARGN})

    if(NOT ARG_GAWK_DIR)
        message(FATAL_ERROR "gawk_generate_build_files: GAWK_DIR is required")
    endif()
    if(NOT ARG_OUT_DIR)
        message(FATAL_ERROR "gawk_generate_build_files: OUT_DIR is required")
    endif()

    get_filename_component(_gawk_abs "${ARG_GAWK_DIR}" ABSOLUTE)
    set(_configure_ac "${_gawk_abs}/configure.ac")
    if(NOT EXISTS "${_configure_ac}")
        message(FATAL_ERROR "configure.ac not found in ${_gawk_abs}")
    endif()

    file(MAKE_DIRECTORY "${ARG_OUT_DIR}")
    file(MAKE_DIRECTORY "${ARG_OUT_DIR}/sys")

    file(READ "${_configure_ac}" _ac_text)
    gawk_parse_ac_init("${_ac_text}" _pkg_name _version _bugreport _tarname)

    set(_dos_flag "")
    if(ARG_TARGET_DOS)
        set(_dos_flag "TARGET_DOS")
    endif()

    gawk_build_config_h(
        PACKAGE_NAME "${_pkg_name}"
        VERSION "${_version}"
        BUGREPORT "${_bugreport}"
        TARNAME "${_tarname}"
        ${_dos_flag}
        OUTPUT_VAR _config_h_text
    )
    file(WRITE "${ARG_OUT_DIR}/config.h" "${_config_h_text}")

    get_filename_component(_pc_dir "${_gawk_abs}/pc" ABSOLUTE)
    file(TO_CMAKE_PATH "${_pc_dir}" _pc_dir_posix)
    foreach(_pc_hdr langinfo.h dlfcn.h socket.h in.h popen.h mbc32.h)
        if(EXISTS "${_pc_dir}/${_pc_hdr}")
            file(WRITE "${ARG_OUT_DIR}/${_pc_hdr}" "#include ${_GAWK_DQ}${_pc_dir_posix}/${_pc_hdr}${_GAWK_DQ}${_GAWK_NL}")
        endif()
    endforeach()

    if(NOT ARG_TARGET_DOS)
        set(_unistd_h [=[#ifndef GAWK_GEN_UNISTD_H
#define GAWK_GEN_UNISTD_H
#include <io.h>
#include <direct.h>
#include <process.h>
#include "posix-core.h"
#ifndef P_WAIT
#define P_WAIT _P_WAIT
#endif
#ifndef P_NOWAIT
#define P_NOWAIT _P_NOWAIT
#endif
#endif
]=])
        file(WRITE "${ARG_OUT_DIR}/unistd.h" "${_unistd_h}")

        set(_strings_h [=[#ifndef GAWK_GEN_STRINGS_H
#define GAWK_GEN_STRINGS_H
#include <string.h>
#ifndef strcasecmp
#define strcasecmp _stricmp
#endif
#ifndef strncasecmp
#define strncasecmp _strnicmp
#endif
#endif
]=])
        file(WRITE "${ARG_OUT_DIR}/strings.h" "${_strings_h}")

        set(_sys_time_h [=[#ifndef GAWK_GEN_SYS_TIME_H
#define GAWK_GEN_SYS_TIME_H
#include "posix-time.h"
#endif
]=])
        file(WRITE "${ARG_OUT_DIR}/sys/time.h" "${_sys_time_h}")

        set(_sys_param_h [=[#ifndef GAWK_GEN_SYS_PARAM_H
#define GAWK_GEN_SYS_PARAM_H
#include <stdlib.h>
#include <limits.h>
#ifndef MAXPATHLEN
#define MAXPATHLEN 260
#endif
#endif
]=])
        file(WRITE "${ARG_OUT_DIR}/sys/param.h" "${_sys_param_h}")
    else()
        gawk_build_dos_compat_c("${_gawk_abs}" _dos_compat_text)
        file(WRITE "${ARG_OUT_DIR}/gawk_dos_compat.c" "${_dos_compat_text}")

        gawk_build_dos_minrx_c("${_gawk_abs}" _dos_minrx_text)
        file(WRITE "${ARG_OUT_DIR}/gawk_dos_minrx.c" "${_dos_minrx_text}")

        set(_io_src "${_gawk_abs}/io.c")
        set(_io_body "")
        if(EXISTS "${_io_src}")
            file(READ "${_io_src}" _io_body)
        endif()
        string(CONCAT _dos_io_text
            "/* Generated gawk_dos_io.c wrapper for 32-bit DOS */${_GAWK_NL}"
            "${_io_body}${_GAWK_NL}"
            "static int wait_any_block_signals(int pid) { return wait_any(pid); }${_GAWK_NL}"
        )
        file(WRITE "${ARG_OUT_DIR}/gawk_dos_io.c" "${_dos_io_text}")
    endif()
endfunction()

# -----------------------------------------------------------------------------
# Script Mode Entry Point (cmake -D... -P cmake/GenerateGawkHeaders.cmake)
#
# Variables supported in script mode:
#   GAWK_DIR             - Path to upstream gawk source directory (required).
#   OUT_DIR              - Output directory for generated headers/sources.
#   TARGET_DOS           - ON/TRUE/1 to generate for 32-bit DOS.
#   FETCH_GAWK           - ON/TRUE/1 to shallow-fetch upstream gawk.
#   GAWK_REV             - Upstream commit SHA or tag when FETCH_GAWK is set.
#   GAWK_REPO_URLS       - Optional semicolon-separated list of repo URLs.
#   GAWK_RETRIES_PER_URL - Optional retry count per URL.
#   GAWK_RETRY_DELAY_SEC - Optional retry delay in seconds.
# -----------------------------------------------------------------------------
if(CMAKE_SCRIPT_MODE_FILE AND CMAKE_SCRIPT_MODE_FILE STREQUAL CMAKE_CURRENT_LIST_FILE)
    if(NOT DEFINED GAWK_DIR OR "${GAWK_DIR}" STREQUAL "")
        message(FATAL_ERROR "Error: GAWK_DIR is required")
    endif()
    if((NOT DEFINED OUT_DIR OR "${OUT_DIR}" STREQUAL "") AND NOT FETCH_GAWK)
        message(FATAL_ERROR "Error: OUT_DIR is required unless FETCH_GAWK is specified")
    endif()

    if(FETCH_GAWK)
        set(_fetch_args DEST_DIR "${GAWK_DIR}")
        if(DEFINED GAWK_REV AND NOT "${GAWK_REV}" STREQUAL "")
            list(APPEND _fetch_args COMMIT "${GAWK_REV}")
        endif()
        if(DEFINED GAWK_REPO_URLS)
            list(APPEND _fetch_args REPO_URLS ${GAWK_REPO_URLS})
        endif()
        if(DEFINED GAWK_RETRIES_PER_URL)
            list(APPEND _fetch_args RETRIES_PER_URL "${GAWK_RETRIES_PER_URL}")
        endif()
        if(DEFINED GAWK_RETRY_DELAY_SEC)
            list(APPEND _fetch_args RETRY_DELAY_SEC "${GAWK_RETRY_DELAY_SEC}")
        endif()
        gawk_ensure_source(${_fetch_args})
    endif()

    if(DEFINED OUT_DIR AND NOT "${OUT_DIR}" STREQUAL "")
        set(_gen_args GAWK_DIR "${GAWK_DIR}" OUT_DIR "${OUT_DIR}")
        if(TARGET_DOS)
            list(APPEND _gen_args TARGET_DOS)
        endif()
        gawk_generate_build_files(${_gen_args})
    endif()
endif()
