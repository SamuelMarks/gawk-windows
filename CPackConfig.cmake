# =============================================================================
# CPackConfig.cmake - Binary Package Configuration for GNU Awk Windows & DOS
#
# Configures CPack to produce standalone portable ZIP archives, NSIS (.exe),
# and WiX (.msi) Windows installers containing the compiled gawk executable
# and licenses.
# =============================================================================

set(CPACK_PACKAGE_NAME "gawk")
set(CPACK_PACKAGE_VENDOR "GNU")
set(CPACK_PACKAGE_VERSION "${PROJECT_VERSION}")
set(CPACK_PACKAGE_VERSION_MAJOR "${PROJECT_VERSION_MAJOR}")
set(CPACK_PACKAGE_VERSION_MINOR "${PROJECT_VERSION_MINOR}")
set(CPACK_PACKAGE_VERSION_PATCH "${PROJECT_VERSION_PATCH}")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "${PROJECT_DESCRIPTION}")
set(CPACK_PACKAGE_HOMEPAGE_URL "${PROJECT_HOMEPAGE_URL}")
set(CPACK_PACKAGE_CONTACT "Samuel Marks")
set(CPACK_PACKAGE_INSTALL_DIRECTORY "gawk")

if(WIN32 AND NOT GAWK_TARGET_DOS)
    set(CPACK_GENERATOR "ZIP;NSIS;WIX")
    set(CPACK_NSIS_DISPLAY_NAME "GNU Awk for Windows")
    set(CPACK_NSIS_PACKAGE_NAME "GNU Awk for Windows")
    set(CPACK_NSIS_MODIFY_PATH ON)
    set(CPACK_WIX_UPGRADE_GUID "8F3A2B61-9C4E-4D1A-8B72-5E1F9A3C4082")
else()
    set(CPACK_GENERATOR "ZIP")
endif()

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
unset(_cpack_license_src)
