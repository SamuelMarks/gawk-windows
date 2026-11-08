GNU Awk (`gawk`) Windows (MSVC) & DOS (OpenWatcom) Native Builds
================================================================

[![License](https://img.shields.io/badge/license-CC0%20OR%20Apache--2.0%20OR%20MIT-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/SamuelMarks/gawk-windows/actions/workflows/ci.yml/badge.svg)](https://github.com/SamuelMarks/gawk-windows/actions/workflows/ci.yml)
![Doc Coverage](https://img.shields.io/badge/doc%20coverage-100%25-brightgreen)
![Test Coverage](https://img.shields.io/badge/test%20coverage-100%25-brightgreen)

This repository provides **native Windows builds** (compiled with Microsoft Visual C++ / MSVC) and **32-bit Protected-Mode DOS builds** (compiled with OpenWatcom v2) of [GNU Awk (`gawk`)](https://www.gnu.org/software/gawk/) (`5.4.60`) using CMake and [auto-win-msvc](https://github.com/SamuelMarks/auto-win-msvc)—**without modifying a single `.c` or `.h` file in the upstream `gawk` repository**.

---

## Features & Architecture

- **Zero Upstream Source Modifications**: All upstream `.c` and `.h` files in `../gawk` remain 100% untouched.
- **No Checked-in `.c` or `.h` Files**: Enforced via the `forbid-c-headers-and-sources` pre-commit hook. All POSIX/BSD/Linux polyfills come from `auto-win-msvc`, and build-time headers (`config.h`, forwarding headers, and DOS wrappers) are deterministically generated into the CMake build directory by `scripts/generate_gawk_headers.py`.
- **Native Windows (MSVC `cl.exe`)**:
  - Activates upstream `gawk` Win32 support (`pc/gawkmisc.pc`, `pc/mbc32.c`, `pc/popen.c`, `pc/dlfcn.h`, `pc/socket.h`) and links against `auto-win-msvc`, `ws2_32.lib`, `kernel32.lib`, `user32.lib`, and `advapi32.lib`.
  - Optional dynamic extensions (`-DGAWK_BUILD_EXTENSIONS=ON`: `ordchr.dll`, `readfile.dll`, `revoutput.dll`, `revtwoway.dll`, `rwarray.dll`, `intdiv.dll`, `time.dll`, `fnmatch.dll`, `inplace.dll`).
- **32-bit Protected-Mode DOS (OpenWatcom v2 `wcl386`)**:
  - Compiles `gawk.exe` as a 32-bit Linear Executable (`LE`) with `DOS32A.EXE` / `DOS4GW.EXE` DOS extender support, `PIPES_SIMULATED=1` (`pc/popen.c`), and C99-to-C89 source transformation via `AutoWinMsvcTransform.cmake`.
  - Verified inside **MS-DOS 1.25**, **MS-DOS 2.0**, and **MS-DOS 4.0** QEMU Vagrant boxes (`vagrant/dos/Vagrantfile`).

---

## Building for Windows (MSVC)

```bat
release.bat
```

Or manually with CMake:

```sh
cmake -B build_msvc -S . -DCMAKE_BUILD_TYPE=Release
cmake --build build_msvc --config Release
ctest --test-dir build_msvc -C Release --output-on-failure
```

---

## Building for 32-bit Protected-Mode DOS (OpenWatcom v2)

```bat
release_dos.bat
```

Or on macOS / Linux with OpenWatcom v2:

```sh
export WATCOM=/path/to/watcom
export PATH="$WATCOM/binl64:$WATCOM/binw:$PATH"
export INCLUDE="$WATCOM/h"
export EDPATH="$WATCOM/eddat"
export WIPFC="$WATCOM/wipfc"

cmake -G "Watcom WMake" -B build_dos -S . \
  -DCMAKE_SYSTEM_NAME=DOS \
  -DCMAKE_SYSTEM_PROCESSOR=I386 \
  -DCMAKE_C_COMPILER="$WATCOM/binl64/wcl386" \
  -DCMAKE_C_FLAGS_INIT="-bt=dos -mf -3r -zq" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF

cmake --build build_dos --config Release
```

---

## License

Dual/triple-licensed under **Apache-2.0**, **MIT**, or **CC0-1.0** for the build scripts and tooling in this repository. Compiled `gawk` binaries are distributed under the **GNU General Public License v3.0 or later (GPL-3.0-or-later)** per upstream GNU Awk.
