#!/usr/bin/env python3
"""Generate config.h, forwarding headers, and DOS compatibility shims for GNU Awk CMake builds."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

DEFAULT_GAWK_REV = "9b2156156f47076b5e588448a89129cc59701a65"
DEFAULT_GAWK_REPOS: tuple[str, ...] = (
    "https://https.git.savannah.gnu.org/git/gawk.git",
    "https://git.savannah.gnu.org/git/gawk.git",
    "git://git.savannah.gnu.org/gawk.git",
)

AC_INIT_RE = re.compile(
    r"^AC_INIT\(\[?([^],]+)\]?,\s*\[?([^],]+)\]?,\s*\[?([^],]+)\]?,\s*\[?([^],)]+)\]?",
    re.MULTILINE,
)


def ensure_gawk_source(
    dest_dir: Path,
    commit: str = DEFAULT_GAWK_REV,
    repo_urls: Sequence[str] = DEFAULT_GAWK_REPOS,
    retries_per_url: int = 3,
    retry_delay_sec: float = 2.0,
) -> Path:
    """Ensure upstream ``gawk`` source is checked out at ``dest_dir``.

    Performs a fast ``git init`` + ``git fetch --depth 1 <url> <commit>`` +
    ``git checkout --force FETCH_HEAD`` against the direct Savannah HTTPS
    endpoint first, avoiding 70 MB un-shallowed history clones and ``git.savannah.gnu.org``
    HTTP 500 gateway timeouts on Windows CI runners. Falls back to a full clone
    over ``git://`` or alternate mirrors with exponential backoff if shallow
    fetching fails.

    Args:
        dest_dir: Destination directory where upstream ``gawk`` will be populated.
        commit: Exact upstream Git commit SHA or tag to check out.
        repo_urls: Ordered sequence of upstream Git repository URLs to try.
        retries_per_url: Number of attempts per repository URL before advancing.
        retry_delay_sec: Base delay in seconds between retry attempts.

    Returns:
        Resolved path to ``dest_dir``.

    Raises:
        RuntimeError: If all repository URLs and retry attempts fail to populate ``awk.h``.
    """
    resolved = dest_dir.resolve()
    if (resolved / "awk.h").is_file() and (resolved / "configure.ac").is_file():
        return resolved

    errors: list[str] = []
    for url in repo_urls:
        for attempt in range(1, retries_per_url + 1):
            if resolved.exists():
                shutil.rmtree(resolved, ignore_errors=True)
            resolved.mkdir(parents=True, exist_ok=True)

            if not url.startswith("git://"):
                init_res = subprocess.run(
                    ["git", "init", str(resolved)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                fetch_res = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(resolved),
                        "-c",
                        "http.lowSpeedLimit=1000",
                        "-c",
                        "http.lowSpeedTime=30",
                        "fetch",
                        "--depth",
                        "1",
                        "--no-tags",
                        url,
                        commit,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if init_res.returncode == 0 and fetch_res.returncode == 0:
                    checkout_res = subprocess.run(
                        ["git", "-C", str(resolved), "checkout", "--force", "FETCH_HEAD"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if checkout_res.returncode == 0 and (resolved / "awk.h").is_file():
                        return resolved
                    errors.append(
                        f"{url} (shallow checkout attempt {attempt}): {checkout_res.stderr.strip()}"
                    )
                else:
                    errors.append(
                        f"{url} (shallow fetch attempt {attempt}): {fetch_res.stderr.strip()}"
                    )
            else:
                clone_res = subprocess.run(
                    ["git", "clone", "--no-checkout", url, str(resolved)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if clone_res.returncode == 0:
                    checkout_res = subprocess.run(
                        ["git", "-C", str(resolved), "checkout", "--force", commit],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if checkout_res.returncode == 0 and (resolved / "awk.h").is_file():
                        return resolved
                    errors.append(
                        f"{url} (clone checkout attempt {attempt}): {checkout_res.stderr.strip()}"
                    )
                else:
                    errors.append(f"{url} (clone attempt {attempt}): {clone_res.stderr.strip()}")

            if retry_delay_sec > 0:
                time.sleep(retry_delay_sec * attempt)

    joined_errors = "; ".join(errors) if errors else "no repository URLs configured"
    raise RuntimeError(f"Failed to fetch upstream gawk ({commit}): {joined_errors}")


def parse_ac_init(configure_ac_text: str) -> tuple[str, str, str, str]:
    """Extract package metadata from ``AC_INIT(...)`` in ``configure.ac``.

    Args:
        configure_ac_text: Full text content of upstream ``configure.ac``.

    Returns:
        Tuple of ``(package_name, version, bugreport, tarname)``.
    """
    match = AC_INIT_RE.search(configure_ac_text)
    if match is None:
        return ("GNU Awk", "5.4.60", "bug-gawk@gnu.org", "gawk")
    return (
        match.group(1).strip(),
        match.group(2).strip(),
        match.group(3).strip(),
        match.group(4).strip(),
    )


def build_config_h(
    package_name: str,
    version: str,
    bugreport: str,
    tarname: str,
    target_dos: bool = False,
) -> str:
    """Build the complete ``config.h`` text for Windows (MSVC/MinGW) or 32-bit DOS.

    Args:
        package_name: Human-readable package name (e.g. ``"GNU Awk"``).
        version: Package version string (e.g. ``"5.4.60"``).
        bugreport: Bug report email address (e.g. ``"bug-gawk@gnu.org"``).
        tarname: Short package tarname (e.g. ``"gawk"``).
        target_dos: ``True`` when generating for 32-bit Protected-Mode DOS, ``False`` for Windows.

    Returns:
        Generated C header text for ``config.h``.
    """
    dq = chr(34)
    nl = chr(10)
    pkg_string = f"{package_name} {version}"
    pkg_url = "http://www.gnu.org/software/gawk/"

    lines: list[str] = [
        "/* Generated config.h for GNU Awk via gawk-windows & auto-win-msvc */",
        "#ifndef GAWK_AUTO_WIN_MSVC_CONFIG_H",
        "#define GAWK_AUTO_WIN_MSVC_CONFIG_H",
        "",
        f"#define PACKAGE {dq}{tarname}{dq}",
        f"#define PACKAGE_NAME {dq}{package_name}{dq}",
        f"#define PACKAGE_TARNAME {dq}{tarname}{dq}",
        f"#define PACKAGE_VERSION {dq}{version}{dq}",
        f"#define VERSION {dq}{version}{dq}",
        f"#define PACKAGE_STRING {dq}{pkg_string}{dq}",
        f"#define PACKAGE_BUGREPORT {dq}{bugreport}{dq}",
        f"#define PACKAGE_URL {dq}{pkg_url}{dq}",
        "",
        "#ifndef DEFPATH",
        f"#define DEFPATH {dq}.{dq}",
        "#endif",
        "#ifndef DEFLIBPATH",
        f"#define DEFLIBPATH {dq}.{dq}",
        "#endif",
        "#ifndef SHLIBEXT",
        f"#define SHLIBEXT {dq}{'dxe' if target_dos else 'dll'}{dq}",
        "#endif",
        "",
        "#define _GNU_SOURCE 1",
        "#define _CRT_SECURE_NO_WARNINGS 1",
        "#define _CRT_NONSTDC_NO_DEPRECATE 1",
        "#define _WINSOCK_DEPRECATED_NO_WARNINGS 1",
        "",
        "#define STDC_HEADERS 1",
        "#define PROTOTYPES 1",
        "#define HAVE_STRINGIZE 1",
        "#define HAVE_STDARG_H 1",
        "#define HAVE_STDBOOL_H 1",
        "#define HAVE_STDDEF_H 1",
        "#define HAVE_STDINT_H 1",
        "#define HAVE_STDIO_H 1",
        "#define HAVE_STDLIB_H 1",
        "#define HAVE_STRING_H 1",
        "#define HAVE_STRINGS_H 1",
        "#define HAVE_INTTYPES_H 1",
        "#define HAVE_INTTYPES_H_WITH_UINTMAX 1",
        "#define HAVE_LIMITS_H 1",
        "#define HAVE_LOCALE_H 1",
        "#define HAVE_MEMORY_H 1",
        "#define HAVE_FCNTL_H 1",
        "#define HAVE_SYS_STAT_H 1",
        "#define HAVE_SYS_TYPES_H 1",
        "#define HAVE_SYS_TIME_H 1",
        "#define HAVE_SYS_PARAM_H 1",
        "#define HAVE_UNISTD_H 1",
        "#define HAVE_WCHAR_H 1",
        "#define HAVE_WCTYPE_H 1",
        "#define HAVE_WCTYPE 1",
        "#define HAVE_WCTYPE_T 1",
        "#define HAVE_WINT_T 1",
        "#define HAVE_BTOWC 1",
        "#define HAVE_ISWCTYPE 1",
        "#define HAVE_ISWLOWER 1",
        "#define HAVE_ISWUPPER 1",
        "#define HAVE_TOWLOWER 1",
        "#define HAVE_TOWUPPER 1",
        "#define HAVE_MBRLEN 1",
        "#define HAVE_MBRTOWC 1",
        "#define HAVE_WCRTOMB 1",
        "#define HAVE_WCSCOLL 1",
        "#define HAVE_ATEXIT 1",
        "#define HAVE_FMOD 1",
        "#define HAVE_ISASCII 1",
        "#define HAVE_ISBLANK 1",
        "#define HAVE_INTMAX_T 1",
        "#define HAVE_UINTMAX_T 1",
        "#define HAVE_LONG_LONG 1",
        "#define HAVE_LONG_LONG_INT 1",
        "#define HAVE_UNSIGNED_LONG_LONG 1",
        "#define HAVE_UNSIGNED_LONG_LONG_INT 1",
        "#define HAVE_MEMCMP 1",
        "#define HAVE_MEMCPY 1",
        "#define HAVE_MEMMOVE 1",
        "#define HAVE_MEMSET 1",
        "#define HAVE_MKTIME 1",
        "#define HAVE_SETENV 1",
        "#define HAVE_SETLOCALE 1",
        "#define HAVE_SNPRINTF 1",
        "#define HAVE_STRCHR 1",
        "#define HAVE_STRCOLL 1",
        "#define HAVE_STRERROR 1",
        "#define HAVE_STRCASECMP 1",
        "#define HAVE_STRNCASECMP 1",
        "#define HAVE_STRSIGNAL 1",
        "#define HAVE_STRTOD 1",
        "#define HAVE_STRTOUL 1",
        "#define HAVE_SYSTEM 1",
        "#undef HAVE_TIMEGM",
        "#define HAVE_TZSET 1",
        "#define HAVE_VPRINTF 1",
        "#define HAVE_GETTIMEOFDAY 1",
        "#define HAVE_LANGINFO_CODESET 1",
        "#define GETPGRP_VOID 1",
        "#define GETGROUPS_T int",
        "#define RETSIGTYPE void",
        "#define SIZEOF_UNSIGNED_INT 4",
        "#define SIZEOF_UNSIGNED_LONG 4",
        "#define TIME_WITH_SYS_TIME 1",
        "#define HAVE_POPEN_H 1",
        "#define strftime rpl_strftime",
        "",
        "/* Disable optional POSIX/GNU features not applicable to standalone Windows/DOS */",
        "#undef ENABLE_NLS",
        "#undef HAVE_LIBINTL_H",
        "#undef HAVE_LIBREADLINE",
        "#undef HAVE_MPFR",
        "#undef USE_PERSISTENT_MALLOC",
        "",
    ]

    if target_dos:
        lines.extend(
            [
                "/* 32-bit Protected-Mode DOS (OpenWatcom / DJGPP) Configuration */",
                "#undef DYNAMIC",
                "#undef HAVE_SOCKETS",
                "#undef HAVE_GETADDRINFO",
                "#undef HAVE_UCHAR_H",
                "#undef HAVE_MBRTOC32",
                "#undef HAVE_C32RTOMB",
                "#undef HAVE_USLEEP",
                "#undef HAVE_TZNAME",
                "#undef HAVE_DECL_TZNAME",
                "#define PIPES_SIMULATED 1",
                "#define HAVE_POPEN_H 1",
                "",
                "#ifndef __STDC__",
                "#define __STDC__ 1",
                "#endif",
                "#ifdef __WATCOMC__",
                "#define __restrict__",
                "#define restrict",
                "#define inline __inline",
                "#ifndef __attribute__",
                "#define __attribute__(x)",
                "#endif",
                "#define _Noreturn",
                "#endif",
                "",
                "#ifndef SIGHUP",
                "#define SIGHUP 1",
                "#endif",
                "#ifndef SIGQUIT",
                "#define SIGQUIT 3",
                "#endif",
                "#ifndef SIGPIPE",
                "#define SIGPIPE 13",
                "#endif",
                "#ifndef SIGKILL",
                "#define SIGKILL 9",
                "#endif",
                "#ifndef WIFEXITED",
                "#define WIFEXITED(w) (((w) & 0xff) == 0)",
                "#endif",
                "#ifndef WIFSIGNALED",
                "#define WIFSIGNALED(w) (((w) & 0x7f) > 0 && (((w) & 0x7f) < 0x7f))",
                "#endif",
                "#ifndef WTERMSIG",
                "#define WTERMSIG(w) ((w) & 0x7f)",
                "#endif",
                "",
                "#include <limits.h>",
                "#include <stdbool.h>",
                "#include <sys/stat.h>",
                "#include <fcntl.h>",
                "#if defined(S_IFSOCK) && S_IFSOCK == 0",
                "#undef S_IFSOCK",
                "#endif",
                "#if defined(S_IFLNK) && S_IFLNK == 0",
                "#undef S_IFLNK",
                "#endif",
                "#if defined(S_IFBLK) && S_IFBLK == 0",
                "#undef S_IFBLK",
                "#define S_IFBLK 0060000",
                "#endif",
                "#ifndef fd_set",
                "typedef unsigned int fd_set;",
                "#define FD_ZERO(set) (*(set) = 0)",
                "#define FD_SET(fd, set) (*(set) |= (1U << ((fd) & 31)))",
                "#define FD_ISSET(fd, set) ((*(set) & (1U << ((fd) & 31))) != 0)",
                "#define select(nfds, rfds, wfds, efds, tv) (1)",
                "#endif",
                "int wait_any(int interesting);",
                "int kill(int pid, int sig);",
                "int pipe(int fds[2]);",
                "int fork(void);",
                "int wait(int *status);",
                '#include "custom.h"',
                "",
                "int getpgrp(void);",
                "#endif /* GAWK_AUTO_WIN_MSVC_CONFIG_H */",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "/* Native Windows (MSVC / clang-cl / MinGW) Configuration */",
                "#define DYNAMIC 1",
                "#define HAVE_SOCKETS 1",
                "#define HAVE_SOCKADDR_STORAGE 1",
                "#define HAVE_GETADDRINFO 1",
                "#define HAVE_GAI_STRERROR 1",
                "#define HAVE_USLEEP 1",
                "#define HAVE_TZNAME 1",
                "#define HAVE_DECL_TZNAME 1",
                "#define PRINTF_HAS_A_FORMAT 1",
                "#define PRINTF_HAS_F_FORMAT 1",
                "",
                "#ifndef __MINGW32__",
                "#define __MINGW32__ 1",
                "#endif",
                "#ifdef _UCRT",
                "#undef _UCRT",
                "#endif",
                "#ifndef __STDC__",
                "#define __STDC__ 1",
                "#endif",
                "",
                "#ifdef _MSC_VER",
                "#define __MINGW32_MAJOR_VERSION 5",
                "#define __restrict__ __restrict",
                "#define restrict __restrict",
                "#define inline __inline",
                "#ifndef __attribute__",
                "#define __attribute__(x)",
                "#endif",
                "#define _Noreturn __declspec(noreturn)",
                "#include <BaseTsd.h>",
                "#ifndef _SSIZE_T_DEFINED",
                "#define _SSIZE_T_DEFINED",
                "typedef SSIZE_T ssize_t;",
                "#endif",
                "#ifndef _MODE_T_DEFINED",
                "#define _MODE_T_DEFINED",
                "typedef unsigned short mode_t;",
                "#endif",
                "#ifndef _PID_T_DEFINED",
                "#define _PID_T_DEFINED",
                "typedef int pid_t;",
                "#endif",
                "#ifndef _USECONDS_T_DEFINED",
                "#define _USECONDS_T_DEFINED",
                "typedef unsigned int useconds_t;",
                "#endif",
                "#include <stdio.h>",
                "#include <fcntl.h>",
                "#include <process.h>",
                "#include <time.h>",
                "#ifndef O_NOINHERIT",
                "#define O_NOINHERIT 0x0080",
                "#endif",
                "#ifndef P_WAIT",
                "#define P_WAIT _P_WAIT",
                "#endif",
                "#ifndef P_NOWAIT",
                "#define P_NOWAIT _P_NOWAIT",
                "#endif",
                "#ifndef tzname",
                "#define tzname _tzname",
                "#endif",
                "#ifndef environ",
                "#define environ _environ",
                "#endif",
                "#ifndef isascii",
                "#define isascii __isascii",
                "#endif",
                "#define setenv gawk_w32_setenv",
                "#define unsetenv gawk_w32_unsetenv",
                "#define xmalloc malloc",
                "#endif /* _MSC_VER */",
                "",
                "#include <limits.h>",
                "#include <stdbool.h>",
                "#include <wchar.h>",
                "#include <wctype.h>",
                "#ifdef _UCRT",
                "#undef _UCRT",
                "#endif",
                '#include "mbc32.h"',
                "#define _UCRT 1",
                '#include "custom.h"',
                "#ifndef GAWK_IN_REPLACE_C",
                "#undef _UCRT",
                "#endif",
                "",
                "#endif /* GAWK_AUTO_WIN_MSVC_CONFIG_H */",
                "",
            ]
        )

    return nl.join(lines)


def build_dos_compat_c(gawk_source_dir: Path) -> str:
    """Build the generated 32-bit DOS OS compatibility C source file.

    Args:
        gawk_source_dir: Path to upstream ``gawk`` source directory.

    Returns:
        Generated C source text implementing DOS ``gawkmisc``, ``nl_langinfo``,
        ``popen``/``pclose``/``system`` wrappers, and POSIX process stubs.
    """
    nl = chr(10)
    popen_c_file = gawk_source_dir / "pc" / "popen.c"
    popen_c_body = popen_c_file.read_text(encoding="utf-8") if popen_c_file.is_file() else ""
    return nl.join(
        [
            "/* Generated gawk_dos_compat.c for 32-bit Protected-Mode DOS (OpenWatcom) */",
            '#include "awk.h"',
            "#include <io.h>",
            "#include <dos.h>",
            "#include <direct.h>",
            "#include <process.h>",
            "",
            "const char quote = '\\'';",
            "const char envsep = ';';",
            "const char *defpath = DEFPATH;",
            "const char *deflibpath = DEFLIBPATH;",
            "",
            "#ifndef INVALID_HANDLE",
            "#define INVALID_HANDLE (-1)",
            "#endif",
            "",
            "const char *",
            "gawk_name(const char *filespec)",
            "{",
            "    char *p = (char *)filespec;",
            "    char *q;",
            "    if ((q = strrchr(p, '\\\\')) != NULL)",
            "        p = q + 1;",
            "    if ((q = strrchr(p, '/')) != NULL && (p == NULL || q > p))",
            "        p = q + 1;",
            "    if ((q = strchr(p, '.')) != NULL)",
            "        *q = '\\0';",
            "    return strlwr(p);",
            "}",
            "",
            "void",
            "os_arg_fixup(int *argcp, char ***argvp)",
            "{",
            "    (void)argcp;",
            "    (void)argvp;",
            "}",
            "",
            "int",
            "os_devopen(const char *name, int flag)",
            "{",
            '    if (strcmp(name, "/dev/null") == 0)',
            '        return open("NUL", flag);',
            "    return INVALID_HANDLE;",
            "}",
            "",
            "size_t",
            "optimal_bufsize(int fd, struct stat *stb)",
            "{",
            "    memset(stb, '\\0', sizeof(struct stat));",
            "    if (fstat(fd, stb) == -1)",
            '        fatal("can\'t stat fd %d (%s)", fd, strerror(errno));',
            "    if (S_ISREG(stb->st_mode) && stb->st_size > 0 && stb->st_size < BUFSIZ)",
            "        return (size_t)stb->st_size;",
            "    return BUFSIZ;",
            "}",
            "",
            "int",
            "ispath(const char *file)",
            "{",
            "    for (; *file; file++) {",
            "        if (*file == '/' || *file == '\\\\' || *file == ':')",
            "            return 1;",
            "    }",
            "    return 0;",
            "}",
            "",
            "int",
            "isdirpunct(int c)",
            "{",
            "    return (c == ':' || c == '\\\\' || c == '/');",
            "}",
            "",
            "void",
            "os_close_on_exec(int fd, const char *name, const char *what, const char *dir)",
            "{",
            "    (void)fd;",
            "    (void)name;",
            "    (void)what;",
            "    (void)dir;",
            "}",
            "",
            "int",
            "os_isdir(int fd)",
            "{",
            "    struct stat sbuf;",
            "    return (fstat(fd, &sbuf) == 0 && S_ISDIR(sbuf.st_mode));",
            "}",
            "",
            "int",
            "os_isreadable(const awk_input_buf_t *iobuf, bool *isdir)",
            "{",
            "    *isdir = false;",
            "    if (iobuf->fd == INVALID_HANDLE)",
            "        return false;",
            "    switch (iobuf->sbuf.st_mode & S_IFMT) {",
            "    case S_IFREG:",
            "    case S_IFCHR:",
            "        return true;",
            "    case S_IFDIR:",
            "        *isdir = true;",
            "        return false;",
            "    default:",
            "        return false;",
            "    }",
            "}",
            "",
            "int",
            "os_is_setuid(void)",
            "{",
            "    return 0;",
            "}",
            "",
            "static int orig_tty_mode = -1;",
            "",
            "int",
            "os_setbinmode(int fd, int mode)",
            "{",
            "    int prev_mode = setmode(fd, mode);",
            "    if (orig_tty_mode == -1 && fd >= 0 && fd <= 2)",
            "        orig_tty_mode = prev_mode;",
            "    return prev_mode;",
            "}",
            "",
            "void",
            "os_restore_mode(int fd)",
            "{",
            "    if (orig_tty_mode != -1)",
            "        setmode(fd, orig_tty_mode);",
            "}",
            "",
            "int",
            "os_isatty(int fd)",
            "{",
            "    return isatty(fd);",
            "}",
            "",
            "int",
            "files_are_same(char *path, SRCFILE *src)",
            "{",
            "    struct stat st;",
            "    if (stat(path, &st) == 0) {",
            "        return (st.st_dev == src->sbuf.st_dev",
            "                && st.st_ino == src->sbuf.st_ino",
            "                && st.st_mtime == src->mtime);",
            "    }",
            "    return 0;",
            "}",
            "",
            "void",
            "init_sockets(void)",
            "{",
            "}",
            "",
            "void",
            "os_maybe_set_errno(void)",
            "{",
            "}",
            "",
            "void",
            "os_disable_aslr(const char *persist_file, char **argv)",
            "{",
            "    (void)persist_file;",
            "    (void)argv;",
            "}",
            "",
            "char *",
            "nl_langinfo(int item)",
            "{",
            "    (void)item;",
            '    return "ASCII";',
            "}",
            "",
            "char *",
            "strsignal(int signo)",
            "{",
            "    switch (signo) {",
            '    case SIGINT: return "SIGINT";',
            '    case SIGILL: return "SIGILL";',
            '    case SIGFPE: return "SIGFPE";',
            '    case SIGSEGV: return "SIGSEGV";',
            '    case SIGTERM: return "SIGTERM";',
            '    case SIGABRT: return "SIGABRT";',
            '    default: return "Unknown signal";',
            "    }",
            "}",
            "",
            "int",
            "wait_any(int interesting)",
            "{",
            "    (void)interesting;",
            "    errno = ECHILD;",
            "    return -1;",
            "}",
            "",
            "int",
            "wait(int *status)",
            "{",
            "    if (status)",
            "        *status = 0;",
            "    errno = ECHILD;",
            "    return -1;",
            "}",
            "",
            "int",
            "kill(int pid, int sig)",
            "{",
            "    (void)pid;",
            "    (void)sig;",
            "    errno = ENOSYS;",
            "    return -1;",
            "}",
            "",
            "int",
            "execl(const char *path, const char *arg0, ...)",
            "{",
            "    (void)path;",
            "    (void)arg0;",
            "    errno = ENOSYS;",
            "    return -1;",
            "}",
            popen_c_body,
            "",
        ]
    )


def build_dos_minrx_c(gawk_source_dir: Path) -> str:
    """Build the C89-compatible ``minrx.c`` wrapper for 32-bit DOS (OpenWatcom).

    Rewrites C99 compound literals ``LITERAL(Subexp) { ... }`` and
    ``LITERAL(QVecInsert) { ... }`` in ``support/minrx.c`` into strict C89
    ``static __inline`` constructor helpers so OpenWatcom C89 mode compiles
    ``minrx.c`` cleanly.

    Args:
        gawk_source_dir: Path to upstream ``gawk`` source directory.

    Returns:
        Generated C source text for ``gawk_dos_minrx.c``.
    """
    nl = chr(10)
    minrx_src = gawk_source_dir / "support" / "minrx.c"
    content = minrx_src.read_text(encoding="utf-8") if minrx_src.is_file() else ""
    if "LITERAL(Subexp)" in content and "awm_make_Subexp(" not in content:
        content = content.replace(
            "struct QVecInsert {" + nl + "\tbool newly;" + nl + "\tNState *newnsp;" + nl + "};",
            "struct QVecInsert {"
            + nl
            + "\tbool newly;"
            + nl
            + "\tNState *newnsp;"
            + nl
            + "};"
            + nl
            + "static __inline QVecInsert awm_make_QVecInsert(bool n, NState *p) {"
            " QVecInsert r; r.newly = n; r.newnsp = p; return r; }",
            1,
        )
        content = content.replace(
            "return LITERAL(QVecInsert) {newly, &q->storage[k]};",
            "return awm_make_QVecInsert(newly, &q->storage[k]);",
        )
        content = content.replace(
            "struct Subexp {"
            + nl
            + "\tNodeList nodes;"
            + nl
            + "\tsize_t maxstk;"
            + nl
            + "\tbool hasmin;"
            + nl
            + "};",
            "struct Subexp {"
            + nl
            + "\tNodeList nodes;"
            + nl
            + "\tsize_t maxstk;"
            + nl
            + "\tbool hasmin;"
            + nl
            + "};"
            + nl
            + "static __inline Subexp awm_make_Subexp(NodeList n, size_t m, bool h) {"
            " Subexp r; r.nodes = n; r.maxstk = m; r.hasmin = h; return r; }"
            + nl
            + "static __inline Subexp awm_make_Subexp_empty(void) {"
            " Subexp r; r.nodes.first = NULL; r.nodes.final = NULL;"
            " r.nodes.size = 0; r.maxstk = 0; r.hasmin = false; return r; }",
            1,
        )
        content = content.replace(
            "LITERAL(Subexp) {{NULL, NULL, 0}, 0, false}",
            "awm_make_Subexp_empty()",
        )
        content = re.sub(
            r"LITERAL\(Subexp\)\s*\{\s*([^,{}]+?)\s*,\s*([^,{}]+?)\s*,\s*([^{}]+?)\s*\}",
            r"awm_make_Subexp(\1, \2, \3)",
            content,
        )
    return content


def generate_gawk_build_files(
    gawk_source_dir: Path,
    out_dir: Path,
    target_dos: bool = False,
) -> None:
    """Generate ``config.h``, forwarding headers, and DOS compatibility sources.

    Args:
        gawk_source_dir: Path to upstream ``gawk`` source directory.
        out_dir: Output directory where generated files are written.
        target_dos: ``True`` when generating for 32-bit DOS, ``False`` for Windows.

    Raises:
        FileNotFoundError: If ``gawk_source_dir/configure.ac`` does not exist.
    """
    configure_ac = gawk_source_dir / "configure.ac"
    if not configure_ac.is_file():
        raise FileNotFoundError(f"configure.ac not found in {gawk_source_dir}")

    nl = chr(10)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys_dir = out_dir / "sys"
    sys_dir.mkdir(parents=True, exist_ok=True)

    pkg_name, version, bugreport, tarname = parse_ac_init(configure_ac.read_text(encoding="utf-8"))

    config_h_text = build_config_h(
        package_name=pkg_name,
        version=version,
        bugreport=bugreport,
        tarname=tarname,
        target_dos=target_dos,
    )
    (out_dir / "config.h").write_text(config_h_text, encoding="utf-8")

    pc_dir = (gawk_source_dir / "pc").resolve()
    for pc_hdr in ("langinfo.h", "dlfcn.h", "socket.h", "in.h", "popen.h", "mbc32.h"):
        src_hdr = pc_dir / pc_hdr
        if src_hdr.is_file():
            (out_dir / pc_hdr).write_text(
                f'#include "{src_hdr.as_posix()}"{nl}',
                encoding="utf-8",
            )

    if not target_dos:
        (out_dir / "unistd.h").write_text(
            nl.join(
                [
                    "#ifndef GAWK_GEN_UNISTD_H",
                    "#define GAWK_GEN_UNISTD_H",
                    "#include <io.h>",
                    "#include <direct.h>",
                    "#include <process.h>",
                    '#include "posix-core.h"',
                    "#ifndef P_WAIT",
                    "#define P_WAIT _P_WAIT",
                    "#endif",
                    "#ifndef P_NOWAIT",
                    "#define P_NOWAIT _P_NOWAIT",
                    "#endif",
                    "#endif",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (out_dir / "strings.h").write_text(
            nl.join(
                [
                    "#ifndef GAWK_GEN_STRINGS_H",
                    "#define GAWK_GEN_STRINGS_H",
                    "#include <string.h>",
                    "#ifndef strcasecmp",
                    "#define strcasecmp _stricmp",
                    "#endif",
                    "#ifndef strncasecmp",
                    "#define strncasecmp _strnicmp",
                    "#endif",
                    "#endif",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (sys_dir / "time.h").write_text(
            nl.join(
                [
                    "#ifndef GAWK_GEN_SYS_TIME_H",
                    "#define GAWK_GEN_SYS_TIME_H",
                    '#include "posix-time.h"',
                    "#endif",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (sys_dir / "param.h").write_text(
            nl.join(
                [
                    "#ifndef GAWK_GEN_SYS_PARAM_H",
                    "#define GAWK_GEN_SYS_PARAM_H",
                    "#include <stdlib.h>",
                    "#include <limits.h>",
                    "#ifndef MAXPATHLEN",
                    "#define MAXPATHLEN 260",
                    "#endif",
                    "#endif",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    else:
        (out_dir / "gawk_dos_compat.c").write_text(
            build_dos_compat_c(gawk_source_dir.resolve()),
            encoding="utf-8",
        )
        (out_dir / "gawk_dos_minrx.c").write_text(
            build_dos_minrx_c(gawk_source_dir.resolve()),
            encoding="utf-8",
        )
        io_src = gawk_source_dir.resolve() / "io.c"
        io_body = io_src.read_text(encoding="utf-8") if io_src.is_file() else ""
        (out_dir / "gawk_dos_io.c").write_text(
            nl.join(
                [
                    "/* Generated gawk_dos_io.c wrapper for 32-bit DOS */",
                    io_body,
                    "static int wait_any_block_signals(int pid) { return wait_any(pid); }",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for ``generate_gawk_headers``.

    Args:
        argv: Optional sequence of CLI arguments.

    Returns:
        Parsed ``argparse.Namespace``.
    """
    parser = argparse.ArgumentParser(
        description="Generate config.h and forwarding headers for GNU Awk."
    )
    parser.add_argument(
        "--gawk-dir",
        type=Path,
        required=True,
        help="Path to upstream gawk source directory.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for generated headers and sources.",
    )
    parser.add_argument(
        "--dos",
        action="store_true",
        help="Generate configuration and shims for 32-bit Protected-Mode DOS.",
    )
    parser.add_argument(
        "--fetch-gawk",
        action="store_true",
        help="Shallow-fetch upstream gawk into --gawk-dir with multi-mirror retry.",
    )
    parser.add_argument(
        "--gawk-rev",
        type=str,
        default=DEFAULT_GAWK_REV,
        help="Upstream gawk Git commit SHA or tag to fetch when --fetch-gawk is used.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``generate_gawk_headers`` CLI entry point.

    Args:
        argv: Optional sequence of CLI arguments.

    Returns:
        Exit status code (``0`` on success, ``1`` on error).
    """
    args = parse_args(argv)
    if args.out_dir is None and not args.fetch_gawk:
        print("Error: --out-dir is required unless --fetch-gawk is specified", file=sys.stderr)
        return 1
    try:
        if args.fetch_gawk:
            ensure_gawk_source(args.gawk_dir, commit=args.gawk_rev)
        if args.out_dir is not None:
            generate_gawk_build_files(args.gawk_dir, args.out_dir, target_dos=args.dos)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
