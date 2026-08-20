# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from kcompare.discover import collect_kconfig_files
from kcompare.discover import prepare_kconfig_env
from kcompare.discover import write_source_file


def test_collect_and_prepare(idf_newer: Path, tmp_path: Path) -> None:
    kconfigs, projbuilds, renames = collect_kconfig_files(str(idf_newer), "esp32")
    assert any(p.endswith("foo/Kconfig") or p.endswith("foo\\Kconfig") for p in kconfigs)
    assert any("Kconfig.projbuild" in p for p in projbuilds)
    assert any(p.endswith("sdkconfig.rename.esp32") for p in renames)
    assert not any(p.endswith("sdkconfig.rename.esp32c3") for p in renames)

    staging = tmp_path / "staging"
    env, rename_paths = prepare_kconfig_env(str(idf_newer), "esp32", str(staging))
    assert env["IDF_TARGET"] == "esp32"
    assert env["IDF_INIT_VERSION"] == "0.0.0-newer"
    assert Path(env["COMPONENT_KCONFIGS_SOURCE_FILE"]).is_file()
    content = Path(env["COMPONENT_KCONFIGS_SOURCE_FILE"]).read_text(encoding="utf-8")
    assert "source " in content
    assert rename_paths


def test_write_source_file_empty(tmp_path: Path) -> None:
    dest = tmp_path / "empty.in"
    write_source_file([], str(dest))
    assert dest.read_text(encoding="utf-8") == ""
