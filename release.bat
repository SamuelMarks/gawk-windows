@echo off
REM ===========================================================================
REM release.bat - Native Windows MSVC Build, Test, and Packaging Script for gawk
REM ===========================================================================

setlocal enabledelayedexpansion

set GAWK_REF=%~1
if "%GAWK_REF%"=="" set GAWK_REF=gawk-5.4.60

echo ==============================================
echo Building gawk Windows Release (%GAWK_REF%)
echo ==============================================

set CMAKE_EXTRA_ARGS=

if exist ..\auto-win-msvc\CMakeLists.txt (
    echo Using local ..\auto-win-msvc repository...
    set CMAKE_EXTRA_ARGS=!CMAKE_EXTRA_ARGS! -DFETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC=..\auto-win-msvc
) else if exist auto-win-msvc\CMakeLists.txt (
    set CMAKE_EXTRA_ARGS=!CMAKE_EXTRA_ARGS! -DFETCHCONTENT_SOURCE_DIR_AUTO_WIN_MSVC=auto-win-msvc
)

set BUILD_DIR=build_release
if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%

echo Configuring with CMake...
cmake -B %BUILD_DIR% -S . -DCMAKE_BUILD_TYPE=Release !CMAKE_EXTRA_ARGS!
if errorlevel 1 exit /b 1

echo Compiling gawk Release...
cmake --build %BUILD_DIR% --config Release
if errorlevel 1 exit /b 1

echo Testing gawk...
ctest --test-dir %BUILD_DIR% -C Release --output-on-failure
if errorlevel 1 exit /b 1

echo Packaging with CPack...
cd %BUILD_DIR%
cpack -C Release -G ZIP -D CPACK_PACKAGE_FILE_NAME=gawk-5.4.60-X64
cpack -C Release -G NSIS -D CPACK_PACKAGE_FILE_NAME=gawk-5.4.60-X64-setup
cpack -C Release -G WIX -D CPACK_PACKAGE_FILE_NAME=gawk-5.4.60-X64
copy /y Release\gawk.exe gawk-5.4.60-X64.exe >nul
cd ..

echo Build and packaging complete!
