# =============================================================================
# CPackSourceConfig.cmake - Source Archive Configuration for gawk Windows
# =============================================================================

set(CPACK_SOURCE_GENERATOR "ZIP;TGZ")
set(CPACK_SOURCE_PACKAGE_FILE_NAME "gawk-5.4.60-src")
set(CPACK_SOURCE_IGNORE_FILES
    "/\\.git/"
    "/build.*/"
    "/\\.vscode/"
    "/\\.idea/"
    "/__pycache__/"
    "/\\.DS_Store"
)
