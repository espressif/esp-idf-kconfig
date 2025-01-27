# SPDX-FileCopyrightText: 2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from kconfcheck.core import _prepare_deprecated_options
from kconfcheck.core import check_deprecated_options

CURRENT_PATH = os.path.abspath(os.path.dirname(__file__))
TEST_FILES_LOCATION = os.path.join(CURRENT_PATH, "sdkconfigs", "check_deprecated")


class TestDeprecatedDetection:
    @pytest.mark.parametrize(
        "defaults_file_name", ["sdkconfig.defaults.with_deprecated", "sdkconfig.defaults.without_deprecated"]
    )
    def test_check_deprecated_options(self, defaults_file_name, monkeypatch):
        monkeypatch.setenv("IDF_PATH", TEST_FILES_LOCATION)

        test_file_path = os.path.join(TEST_FILES_LOCATION, defaults_file_name)
        rename_file_path = os.path.join(TEST_FILES_LOCATION, "sdkconfig.rename")
        files, deprecated_options, ignore_dirs = _prepare_deprecated_options(
            None, None, [test_file_path, rename_file_path]
        )
        assert len(files) == 1
        is_valid = check_deprecated_options(files[0], deprecated_options, ignore_dirs)
        # if the defaults file contains deprecated options, it should return False
        if defaults_file_name == "sdkconfig.defaults.with_deprecated":
            assert not is_valid
        elif defaults_file_name == "sdkconfig.defaults.without_deprecated":
            assert is_valid
        else:
            raise ValueError("Invalid defaults file name")
