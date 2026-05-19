# SPDX-FileCopyrightText: 2025-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from kconfcheck.check_deprecated_options import _prepare_deprecated_options
from kconfcheck.check_deprecated_options import check_deprecated_options

CURRENT_PATH = os.path.abspath(os.path.dirname(__file__))
TEST_FILES_LOCATION = os.path.join(CURRENT_PATH, "sdkconfigs", "check_deprecated")
SCOPED_TEST_LOCATION = os.path.join(CURRENT_PATH, "sdkconfigs", "check_deprecated_scoped")


class TestDeprecatedDetection:
    @pytest.mark.parametrize(
        "defaults_file_name", ["sdkconfig.defaults.with_deprecated", "sdkconfig.defaults.without_deprecated"]
    )
    def test_check_deprecated_options(self, defaults_file_name, monkeypatch):
        monkeypatch.setenv("IDF_PATH", TEST_FILES_LOCATION)

        test_file_path = os.path.join(TEST_FILES_LOCATION, defaults_file_name)
        rename_file_path = os.path.join(TEST_FILES_LOCATION, "sdkconfig.rename")
        files, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path = (
            _prepare_deprecated_options(None, None, [test_file_path, rename_file_path])
        )
        assert len(files) == 1
        is_valid = check_deprecated_options(
            files[0], global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path
        )
        if defaults_file_name == "sdkconfig.defaults.with_deprecated":
            assert not is_valid
        elif defaults_file_name == "sdkconfig.defaults.without_deprecated":
            assert is_valid
        else:
            raise ValueError("Invalid defaults file name")


class TestScopedDeprecation:
    """Tests that rename files under project roots only apply to their own subtree."""

    def test_cross_project_isolation(self, monkeypatch):
        """project_b's sdkconfig.defaults uses CONFIG_A_OLD (deprecated only in project_a) -> passes"""
        monkeypatch.setenv("IDF_PATH", SCOPED_TEST_LOCATION)

        files, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path = (
            _prepare_deprecated_options(None, None, [])
        )

        file_path = os.path.join(SCOPED_TEST_LOCATION, "examples", "project_b", "sdkconfig.defaults")
        result = check_deprecated_options(
            file_path, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path
        )
        assert result is True

    def test_local_enforcement(self, monkeypatch):
        """project_a's sdkconfig.defaults uses CONFIG_A_OLD (deprecated in same project) -> fails"""
        monkeypatch.setenv("IDF_PATH", SCOPED_TEST_LOCATION)

        files, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path = (
            _prepare_deprecated_options(None, None, [])
        )

        file_path = os.path.join(SCOPED_TEST_LOCATION, "examples", "project_a", "sdkconfig.defaults")
        result = check_deprecated_options(
            file_path, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path
        )
        assert result is False

    def test_global_enforcement(self, monkeypatch):
        """project_b's sdkconfig.defaults.global_dep uses CONFIG_GLOBAL_OLD (global from component) -> fails"""
        monkeypatch.setenv("IDF_PATH", SCOPED_TEST_LOCATION)

        files, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path = (
            _prepare_deprecated_options(None, None, [])
        )

        file_path = os.path.join(SCOPED_TEST_LOCATION, "examples", "project_b", "sdkconfig.defaults.global_dep")
        result = check_deprecated_options(
            file_path, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path
        )
        assert result is False

    def test_no_project_root_uses_global_only(self, monkeypatch):
        """A file outside any project root is checked against only the global deprecated set."""
        monkeypatch.setenv("IDF_PATH", SCOPED_TEST_LOCATION)

        files, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path = (
            _prepare_deprecated_options(None, None, [])
        )

        file_path = os.path.join(SCOPED_TEST_LOCATION, "sdkconfig.defaults.top_level")
        result = check_deprecated_options(
            file_path, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path
        )
        assert result is False

    def test_orphan_rename_is_invisible(self, monkeypatch):
        """A rename file that lives outside IDF root, outside components/, and outside any
        project subtree (e.g. ``examples/common_components/...``) is never discovered when no
        file inside it is being checked. Its deprecated names appear in neither the global
        nor any lazily-built local set, and **no diagnostic is emitted** — silence is the
        expected behavior in the on-demand model."""
        monkeypatch.setenv("IDF_PATH", SCOPED_TEST_LOCATION)

        files, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path = (
            _prepare_deprecated_options(None, None, [])
        )

        # Trigger lazy local builds for both example projects so the assertion below is meaningful.
        for sub in ("project_a", "project_b"):
            check_deprecated_options(
                os.path.join(SCOPED_TEST_LOCATION, "examples", sub, "sdkconfig.defaults"),
                global_deprecated,
                local_deprecated,
                ignore_dirs,
                project_root_cache,
                abs_idf_path,
            )

        orphan_name = "CONFIG_ORPHAN_OLD"
        assert orphan_name not in global_deprecated
        assert all(orphan_name not in s for s in local_deprecated.values())

    def test_explicit_cli_rename_is_global(self, monkeypatch):
        """A sdkconfig.rename file passed explicitly on the command line is treated as global:
        its deprecated names apply to every checked file regardless of location. This is the
        semantic agreed for explicit args and --includes-discovered rename files."""
        monkeypatch.setenv("IDF_PATH", SCOPED_TEST_LOCATION)

        orphan_rename = os.path.join(
            SCOPED_TEST_LOCATION, "examples", "common_components", "shared_helper", "sdkconfig.rename"
        )
        files, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path = (
            _prepare_deprecated_options(None, None, [orphan_rename])
        )

        assert "CONFIG_ORPHAN_OLD" in global_deprecated
        # Rename files must be stripped from the to-check list.
        assert orphan_rename not in files
