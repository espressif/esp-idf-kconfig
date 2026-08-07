# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Tests for kcompare.detect (ESP-IDF root detection).
"""

from pathlib import Path

from kcompare.detect import is_idf_root


def test_is_idf_root_true(tmp_path: Path) -> None:
    (tmp_path / "Kconfig").write_text("mainmenu\n")
    tools_cmake = tmp_path / "tools" / "cmake"
    tools_cmake.mkdir(parents=True)
    (tools_cmake / "project.cmake").write_text("")
    assert is_idf_root(str(tmp_path)) is True


def test_is_idf_root_missing_kconfig(tmp_path: Path) -> None:
    tools_cmake = tmp_path / "tools" / "cmake"
    tools_cmake.mkdir(parents=True)
    (tools_cmake / "project.cmake").write_text("")
    assert is_idf_root(str(tmp_path)) is False


def test_is_idf_root_missing_project_cmake(tmp_path: Path) -> None:
    (tmp_path / "Kconfig").write_text("mainmenu\n")
    assert is_idf_root(str(tmp_path)) is False
