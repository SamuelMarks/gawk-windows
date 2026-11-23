"""Unit tests for ``cmake/GenerateGawkHeaders.cmake``."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CMAKE_SCRIPT = REPO_ROOT / "cmake" / "GenerateGawkHeaders.cmake"


def run_cmake_generator(*args: str) -> subprocess.CompletedProcess[str]:
    """Execute ``cmake/GenerateGawkHeaders.cmake`` in CMake script mode.

    Args:
        *args: Additional ``-DVAR=VALUE`` arguments passed before ``-P``.

    Returns:
        CompletedProcess containing stdout, stderr, and return code.
    """
    return subprocess.run(
        ["cmake", *args, "-P", str(CMAKE_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cmake_generate_windows_and_dos(tmp_path: Path) -> None:
    """Verify ``GenerateGawkHeaders.cmake`` generates expected Windows and DOS build files.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    gawk_dir = tmp_path / "gawk"
    pc_dir = gawk_dir / "pc"
    support_dir = gawk_dir / "support"
    pc_dir.mkdir(parents=True)
    support_dir.mkdir(parents=True)

    nl = chr(10)
    tab = chr(9)

    (gawk_dir / "awk.h").write_text(f"/* awk.h */{nl}", encoding="utf-8")
    (gawk_dir / "configure.ac").write_text(
        f"AC_INIT([GNU Awk],[5.4.60],[bug-gawk@gnu.org],[gawk]){nl}",
        encoding="utf-8",
    )
    (pc_dir / "popen.c").write_text(f"/* popen body */{nl}", encoding="utf-8")
    (gawk_dir / "io.c").write_text(f"/* io body */{nl}", encoding="utf-8")
    for hdr in ("langinfo.h", "dlfcn.h", "socket.h", "in.h", "popen.h", "mbc32.h"):
        (pc_dir / hdr).write_text(f"/* {hdr} */{nl}", encoding="utf-8")

    sample_minrx = nl.join(
        [
            "struct QVecInsert {",
            f"{tab}bool newly;",
            f"{tab}NState *newnsp;",
            "};",
            "static QVecInsert foo(QVec *q, size_t k) {",
            "    bool newly = true;",
            "    return LITERAL(QVecInsert) {newly, &q->storage[k]};",
            "}",
            "struct Subexp {",
            f"{tab}NodeList nodes;",
            f"{tab}size_t maxstk;",
            f"{tab}bool hasmin;",
            "};",
            "static Subexp bar(Subexp lh) {",
            "    if (lh.maxstk == 0)",
            "        return LITERAL(Subexp) {{NULL, NULL, 0}, 0, false};",
            "    return LITERAL(Subexp) {lh.nodes, lh.maxstk, lh.hasmin };",
            "}",
            "",
        ]
    )
    (support_dir / "minrx.c").write_text(sample_minrx, encoding="utf-8")

    # 1. Native Windows generation
    out_win = tmp_path / "out_win"
    res_win = run_cmake_generator(f"-DGAWK_DIR={gawk_dir}", f"-DOUT_DIR={out_win}")
    assert res_win.returncode == 0, res_win.stderr
    win_cfg = (out_win / "config.h").read_text(encoding="utf-8")
    assert '#define PACKAGE_STRING "GNU Awk 5.4.60"' in win_cfg
    assert "#define DYNAMIC 1" in win_cfg
    assert "#define __MINGW32__ 1" in win_cfg
    assert "#define _UCRT 1" in win_cfg
    assert (out_win / "langinfo.h").is_file()
    assert (out_win / "unistd.h").is_file()
    assert (out_win / "strings.h").is_file()
    assert (out_win / "sys" / "time.h").is_file()
    assert (out_win / "sys" / "param.h").is_file()

    # 2. 32-bit DOS generation
    out_dos = tmp_path / "out_dos"
    res_dos = run_cmake_generator(
        f"-DGAWK_DIR={gawk_dir}",
        f"-DOUT_DIR={out_dos}",
        "-DTARGET_DOS=ON",
    )
    assert res_dos.returncode == 0, res_dos.stderr
    dos_cfg = (out_dos / "config.h").read_text(encoding="utf-8")
    assert "#ifdef OPENWATCOM_COMPAT_H" in dos_cfg
    assert "#undef remove" in dos_cfg
    assert "#define PIPES_SIMULATED 1" in dos_cfg
    assert "#undef DYNAMIC" in dos_cfg
    assert "#undef HAVE_SOCKETS" in dos_cfg
    assert "#include <stdbool.h>" in dos_cfg

    dos_compat = (out_dos / "gawk_dos_compat.c").read_text(encoding="utf-8")
    assert "gawk_name(const char *filespec)" in dos_compat
    assert "nl_langinfo(int item)" in dos_compat
    assert "/* popen body */" in dos_compat

    dos_minrx = (out_dos / "gawk_dos_minrx.c").read_text(encoding="utf-8")
    assert "awm_make_QVecInsert(newly, &q->storage[k])" in dos_minrx
    assert "awm_make_Subexp_empty()" in dos_minrx
    assert "awm_make_Subexp(lh.nodes, lh.maxstk, lh.hasmin)" in dos_minrx
    assert "LITERAL(Subexp)" not in dos_minrx

    dos_io = (out_dos / "gawk_dos_io.c").read_text(encoding="utf-8")
    assert "/* io body */" in dos_io
    assert "wait_any_block_signals" in dos_io


def test_cmake_fallback_ac_init_and_error_paths(tmp_path: Path) -> None:
    """Verify AC_INIT fallback, already-populated fetch, and script-mode error conditions.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    nl = chr(10)

    # Missing GAWK_DIR
    res_no_gawk = run_cmake_generator()
    assert res_no_gawk.returncode != 0
    assert "GAWK_DIR is required" in res_no_gawk.stderr

    # Missing OUT_DIR and FETCH_GAWK
    gawk_dir = tmp_path / "gawk_fallback"
    gawk_dir.mkdir()
    res_no_out = run_cmake_generator(f"-DGAWK_DIR={gawk_dir}")
    assert res_no_out.returncode != 0
    assert "OUT_DIR is required" in res_no_out.stderr

    # Missing configure.ac
    out_dir = tmp_path / "out_fallback"
    res_missing_ac = run_cmake_generator(f"-DGAWK_DIR={gawk_dir}", f"-DOUT_DIR={out_dir}")
    assert res_missing_ac.returncode != 0
    assert "configure.ac not found" in res_missing_ac.stderr

    # Fallback when configure.ac has no AC_INIT match
    (gawk_dir / "awk.h").write_text(f"/* awk.h */{nl}", encoding="utf-8")
    (gawk_dir / "configure.ac").write_text(f"dnl no AC_INIT here{nl}", encoding="utf-8")
    res_fb = run_cmake_generator(
        f"-DGAWK_DIR={gawk_dir}",
        f"-DOUT_DIR={out_dir}",
        "-DFETCH_GAWK=ON",
    )
    assert res_fb.returncode == 0, res_fb.stderr
    cfg_text = (out_dir / "config.h").read_text(encoding="utf-8")
    assert '#define PACKAGE_STRING "GNU Awk 5.4.60"' in cfg_text

    # Fetch failure when pointing at an invalid local repository URL
    empty_dest = tmp_path / "fetch_fail_dest"
    res_fetch_fail = run_cmake_generator(
        f"-DGAWK_DIR={empty_dest}",
        "-DFETCH_GAWK=ON",
        "-DGAWK_REV=deadbeef",
        f"-DGAWK_REPO_URLS={tmp_path / 'nonexistent_repo.git'}",
        "-DGAWK_RETRIES_PER_URL=1",
        "-DGAWK_RETRY_DELAY_SEC=0",
    )
    assert res_fetch_fail.returncode != 0
    assert "Failed to fetch upstream gawk" in res_fetch_fail.stderr


def test_cmakelists_uses_target_scoped_commands() -> None:
    """Verify repository CMake configurations use target_* commands instead of globals."""
    cmake_lists = (REPO_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    vagrantfile = (REPO_ROOT / "vagrant" / "dos" / "Vagrantfile").read_text(encoding="utf-8")
    cpack_cfg = (REPO_ROOT / "CPackConfig.cmake").read_text(encoding="utf-8")
    cpack_src_cfg = (REPO_ROOT / "CPackSourceConfig.cmake").read_text(encoding="utf-8")

    forbidden_patterns = (
        r"(?m)^\s*include_directories\s*\(",
        r"(?m)^\s*link_directories\s*\(",
        r"(?m)^\s*link_libraries\s*\(",
        r"(?m)^\s*add_definitions\s*\(",
        r"(?m)^\s*add_compile_definitions\s*\(",
        r"(?m)^\s*add_compile_options\s*\(",
        r"(?m)^\s*add_link_options\s*\(",
        r"(?m)^\s*set_source_files_properties\s*\(",
        r"CMAKE_C_STANDARD",
        r"CMAKE_POLICY_VERSION_MINIMUM",
        r"CMAKE_C_FLAGS_DEBUG",
        r"CMAKE_EXE_LINKER_FLAGS_DEBUG",
        r"FETCHCONTENT_SOURCE_DIR_AUTO-WIN-MSVC",
        r"\bGAWK_VERSION\b",
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, cmake_lists) is None, f"Forbidden global pattern: {pattern}"

    required_target_commands = (
        "target_sources(",
        "target_include_directories(",
        "target_compile_definitions(",
        "target_compile_options(",
        "target_compile_features(",
        "target_link_options(",
        "target_link_libraries(",
    )
    for cmd in required_target_commands:
        assert cmd in cmake_lists, f"Expected modern {cmd} in CMakeLists.txt"

    assert "CMAKE_C_STANDARD" not in vagrantfile
    assert "${PROJECT_VERSION}" in cpack_cfg
    assert "${PROJECT_VERSION}" in cpack_src_cfg
