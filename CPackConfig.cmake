# =============================================================================
# CPackConfig.cmake - Binary Package Configuration for GNU Awk Windows & DOS
#
# Configures CPack to produce standalone portable ZIP archives, NSIS (.exe),
# and WiX (.msi) Windows installers containing the compiled gawk executable
# and licenses.
# =============================================================================

set(CPACK_PACKAGE_NAME "gawk")
set(CPACK_PACKAGE_VENDOR "GNU")
set(CPACK_PACKAGE_VERSION "5.4.60")
set(CPACK_PACKAGE_VERSION_MAJOR "5")
set(CPACK_PACKAGE_VERSION_MINOR "4")
set(CPACK_PACKAGE_VERSION_PATCH "60")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "GNU Awk pattern scanning and processing language for native Windows (MSVC) and 32-bit DOS (OpenWatcom).")
set(CPACK_PACKAGE_HOMEPAGE_URL "https://www.gnu.org/software/gawk/")
set(CPACK_PACKAGE_CONTACT "Samuel Marks")
set(CPACK_PACKAGE_INSTALL_DIRECTORY "gawk")
set(CPACK_GENERATOR "ZIP;NSIS;WIX")

set(_cpack_license_src "")
if(DEFINED GAWK_SOURCE_DIR AND EXISTS "${GAWK_SOURCE_DIR}/COPYING")
    set(_cpack_license_src "${GAWK_SOURCE_DIR}/COPYING")
elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-MIT")
    set(_cpack_license_src "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-MIT")
endif()

if(_cpack_license_src)
    if(DEFINED CMAKE_CURRENT_BINARY_DIR AND NOT "${CMAKE_CURRENT_BINARY_DIR}" STREQUAL "${CMAKE_CURRENT_SOURCE_DIR}")
        configure_file("${_cpack_license_src}" "${CMAKE_CURRENT_BINARY_DIR}/LICENSE.txt" COPYONLY)
        set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_CURRENT_BINARY_DIR}/LICENSE.txt")
    else()
        set(CPACK_RESOURCE_FILE_LICENSE "${_cpack_license_src}")
    endif()
endif()

set(CPACK_NSIS_DISPLAY_NAME "GNU Awk for Windows")
set(CPACK_NSIS_PACKAGE_NAME "GNU Awk for Windows")
set(CPACK_NSIS_MODIFY_PATH ON)

set(CPACK_WIX_UPGRADE_GUID "8F3A2B61-9C4E-4D1A-8B72-5E1F9A3C4082")
