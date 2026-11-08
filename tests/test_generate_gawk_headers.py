"""Unit tests for ``scripts.generate_gawk_headers``."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from scripts.generate_gawk_headers import (
    build_config_h,
    build_dos_compat_c,
    build_dos_minrx_c,
    generate_gawk_build_files,
    main,
    parse_ac_init,
    parse_args,
)


def test_parse_ac_init_valid_and_fallback() -> None:
    """Verify ``parse_ac_init`` extracts metadata from ``AC_INIT`` and falls back cleanly."""
    sample = "AC_INIT([GNU Awk],[5.4.60],[bug-gawk@gnu.org],[gawk])\n"
    assert parse_ac_init(sample) == ("GNU Awk", "5.4.60", "bug-gawk@gnu.org", "gawk")
    assert parse_ac_init("dnl empty file\n") == (
        "GNU Awk",
        "5.4.60",
        "bug-gawk@gnu.org",
        "gawk",
    )


def test_build_config_h_windows_and_dos() -> None:
    """Verify ``build_config_h`` produces expected macros for Windows and DOS modes."""
    win_cfg = build_config_h("GNU Awk", "5.4.60", "bug-gawk@gnu.org", "gawk", target_dos=False)
    assert '#define PACKAGE_STRING "GNU Awk 5.4.60"' in win_cfg
    assert "#define DYNAMIC 1" in win_cfg
    assert "#define __MINGW32__ 1" in win_cfg
    assert "#define _UCRT 1" in win_cfg

    dos_cfg = build_config_h("GNU Awk", "5.4.60", "bug-gawk@gnu.org", "gawk", target_dos=True)
    assert "#define PIPES_SIMULATED 1" in dos_cfg
    assert "#undef DYNAMIC" in dos_cfg
    assert "#undef HAVE_SOCKETS" in dos_cfg
    assert "#include <stdbool.h>" in dos_cfg


def test_build_dos_compat_c(tmp_path: Path) -> None:
    """Verify ``build_dos_compat_c`` includes DOS OS functions and ``pc/`` paths."""
    pc_dir = tmp_path / "pc"
    pc_dir.mkdir(parents=True, exist_ok=True)
    (pc_dir / "popen.c").write_text("/* popen body */\n", encoding="utf-8")
    src_text = build_dos_compat_c(tmp_path)
    assert "gawk_name(const char *filespec)" in src_text
    assert "nl_langinfo(int item)" in src_text
    assert "/* popen body */" in src_text


def test_build_dos_minrx_c(tmp_path: Path) -> None:
    """Verify ``build_dos_minrx_c`` lowers C99 compound literals in ``minrx.c``."""
    assert build_dos_minrx_c(tmp_path) == ""
    support_dir = tmp_path / "support"
    support_dir.mkdir(parents=True, exist_ok=True)
    sample_minrx = (
        "struct QVecInsert {\n\tbool newly;\n\tNState *newnsp;\n};\n"
        "static QVecInsert foo(QVec *q, size_t k) {\n"
        "    bool newly = true;\n"
        "    return LITERAL(QVecInsert) {newly, &q->storage[k]};\n"
        "}\n"
        "struct Subexp {\n\tNodeList nodes;\n\tsize_t maxstk;\n\tbool hasmin;\n};\n"
        "static Subexp bar(Subexp lh) {\n"
        "    if (lh.maxstk == 0)\n"
        "        return LITERAL(Subexp) {{NULL, NULL, 0}, 0, false};\n"
        "    return LITERAL(Subexp) {lh.nodes, lh.maxstk, lh.hasmin};\n"
        "}\n"
    )
    (support_dir / "minrx.c").write_text(sample_minrx, encoding="utf-8")
    lowered = build_dos_minrx_c(tmp_path)
    assert "awm_make_QVecInsert(newly, &q->storage[k])" in lowered
    assert "awm_make_Subexp_empty()" in lowered
    assert "awm_make_Subexp(lh.nodes, lh.maxstk, lh.hasmin)" in lowered
    assert "LITERAL(Subexp)" not in lowered
    (support_dir / "minrx.c").write_text(lowered, encoding="utf-8")
    assert build_dos_minrx_c(tmp_path) == lowered


def test_generate_gawk_build_files_windows_and_dos(tmp_path: Path) -> None:
    """Verify ``generate_gawk_build_files`` writes headers for Windows and DOS targets."""
    gawk_dir = tmp_path / "gawk"
    pc_dir = gawk_dir / "pc"
    pc_dir.mkdir(parents=True)
    (gawk_dir / "configure.ac").write_text(
        "AC_INIT([GNU Awk],[5.4.60],[bug-gawk@gnu.org],[gawk])\n",
        encoding="utf-8",
    )
    for hdr in ("langinfo.h", "dlfcn.h", "socket.h", "in.h", "popen.h", "mbc32.h"):
        (pc_dir / hdr).write_text(f"/* {hdr} */\n", encoding="utf-8")

    out_win = tmp_path / "out_win"
    generate_gawk_build_files(gawk_dir, out_win, target_dos=False)
    assert (out_win / "config.h").is_file()
    assert (out_win / "langinfo.h").is_file()
    assert (out_win / "unistd.h").is_file()
    assert (out_win / "strings.h").is_file()
    assert (out_win / "sys" / "time.h").is_file()
    assert (out_win / "sys" / "param.h").is_file()

    out_dos = tmp_path / "out_dos"
    generate_gawk_build_files(gawk_dir, out_dos, target_dos=True)
    assert (out_dos / "config.h").is_file()
    assert (out_dos / "gawk_dos_compat.c").is_file()
    assert (out_dos / "gawk_dos_minrx.c").is_file()


def test_generate_gawk_build_files_missing_configure(tmp_path: Path) -> None:
    """Verify ``generate_gawk_build_files`` raises ``FileNotFoundError`` when missing."""
    with pytest.raises(FileNotFoundError):
        generate_gawk_build_files(tmp_path / "nonexistent", tmp_path / "out")


def test_parse_args_and_main(tmp_path: Path) -> None:
    """Verify ``parse_args`` and ``main`` return codes for valid and missing paths."""
    gawk_dir = tmp_path / "gawk"
    gawk_dir.mkdir()
    (gawk_dir / "configure.ac").write_text(
        "AC_INIT([GNU Awk],[5.4.60],[bug-gawk@gnu.org],[gawk])\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    parsed = parse_args(["--gawk-dir", str(gawk_dir), "--out-dir", str(out_dir), "--dos"])
    assert parsed.gawk_dir == gawk_dir
    assert parsed.out_dir == out_dir
    assert parsed.dos is True

    assert main(["--gawk-dir", str(gawk_dir), "--out-dir", str(out_dir)]) == 0
    assert main(["--gawk-dir", str(tmp_path / "missing"), "--out-dir", str(out_dir)]) == 1


def test_module_main_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ``__main__`` entry point execution via ``runpy``."""
    gawk_dir = tmp_path / "gawk"
    gawk_dir.mkdir()
    (gawk_dir / "configure.ac").write_text(
        "AC_INIT([GNU Awk],[5.4.60],[bug-gawk@gnu.org],[gawk])\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        ["generate_gawk_headers.py", "--gawk-dir", str(gawk_dir), "--out-dir", str(out_dir)],
    )
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("scripts.generate_gawk_headers", run_name="__main__")
    assert exc_info.value.code == 0
