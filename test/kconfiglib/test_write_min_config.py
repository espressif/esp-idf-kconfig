# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for :meth:`Kconfig.write_min_config` (normalization, labels, headers)."""

import os
import textwrap
from pathlib import Path
from typing import Generator

import pytest

from esp_kconfiglib import Kconfig

_TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
_KCONFIGS_PATH = os.path.join(_TEST_FILES_PATH, "kconfigs")


class TestBase:
    @pytest.fixture(scope="class", autouse=True)
    def version(self, request: pytest.FixtureRequest) -> Generator[None, None, None]:
        os.environ["KCONFIG_PARSER_VERSION"] = request.param
        yield
        del os.environ["KCONFIG_PARSER_VERSION"]


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestWriteMinConfigKconfiglib(TestBase):
    """``write_min_config`` normalization, labels, headers (both parsers)."""

    @staticmethod
    def _write_kconfig(tmp_path: Path, body: str) -> Path:
        path = tmp_path / "Kconfig"
        path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
        return path

    def test_normalize_unset_emits_equals_n(self, tmp_path: Path) -> None:
        """``normalize_unset=True`` turns ``# CONFIG_FOO is not set`` into ``CONFIG_FOO=n``."""
        kpath = self._write_kconfig(
            tmp_path,
            """
            mainmenu "M"

                config DEFAULT_ON
                    bool "on"
                    default y
            """,
        )
        kconf = Kconfig(str(kpath))
        kconf.syms["DEFAULT_ON"].set_value("n")

        out = tmp_path / "sdkconfig.defaults"
        kconf.write_min_config(str(out), header="# H\n", normalize_unset=True)
        text = out.read_text()

        assert "CONFIG_DEFAULT_ON=n" in text
        assert "is not set" not in text

    def test_labels_with_normalize_unset(self, tmp_path: Path) -> None:
        """``labels=True`` and ``normalize_unset=True`` can be used together."""
        kpath = self._write_kconfig(
            tmp_path,
            """
            mainmenu "M"

                menu "Section"
                    config DEFAULT_ON
                        bool "on"
                        default y
                endmenu
            """,
        )
        kconf = Kconfig(str(kpath))
        kconf.syms["DEFAULT_ON"].set_value("n")

        out = tmp_path / "sdkconfig.defaults"
        kconf.write_min_config(str(out), header="# H\n", labels=True, normalize_unset=True)
        text = out.read_text()

        assert "# Section" in text
        assert "# end of Section" in text
        assert "CONFIG_DEFAULT_ON=n" in text
        assert "is not set" not in text

    def test_write_min_config_no_labels_skips_menu_markers(self, tmp_path: Path) -> None:
        """Default ``labels=False`` does not emit menu section banners."""
        kpath = self._write_kconfig(
            tmp_path,
            """
            mainmenu "M"

                menu "Section"
                    config DEFAULT_ON
                        bool "on"
                        default y
                endmenu
            """,
        )
        kconf = Kconfig(str(kpath))
        kconf.syms["DEFAULT_ON"].set_value("n")

        out = tmp_path / "sdkconfig.defaults"
        kconf.write_min_config(str(out), header="# H\n", normalize_unset=True)
        text = out.read_text()

        assert "# Section" not in text
        assert "# end of" not in text
        assert "CONFIG_DEFAULT_ON=n" in text

    def test_unset_normalized_to_n_fixture(self, tmp_path: Path) -> None:
        """``# CONFIG_FOO is not set`` lines are rewritten to ``CONFIG_FOO=n`` (fixture Kconfig)."""
        kconfig = Kconfig(os.path.join(_KCONFIGS_PATH, "Kconfig.idf_min_config"))
        kconfig.syms["MOTORS_ENABLED"].set_value("y")
        out = tmp_path / "sdkconfig.defaults"
        kconfig.write_min_config(str(out), normalize_unset=True)

        for line in out.read_text().splitlines():
            assert "is not set" not in line

    def test_custom_header_passed_through(self, tmp_path: Path) -> None:
        """A caller-supplied header appears verbatim at the top of the file."""
        kconfig = Kconfig(os.path.join(_KCONFIGS_PATH, "Kconfig.idf_min_config"))
        kconfig.syms["MOTORS_ENABLED"].set_value("y")
        out = tmp_path / "sdkconfig.defaults"
        kconfig.write_min_config(str(out), header="# custom header\n")

        contents = out.read_text()
        assert contents.startswith("# custom header\n")

    def test_no_change_message(self, tmp_path: Path) -> None:
        """Second write returns 'no change' message when content is identical."""
        kconfig = Kconfig(os.path.join(_KCONFIGS_PATH, "Kconfig.idf_min_config"))
        kconfig.syms["MOTORS_ENABLED"].set_value("y")
        out = tmp_path / "sdkconfig.defaults"

        msg1 = kconfig.write_min_config(str(out))
        assert "saved" in msg1.lower()

        msg2 = kconfig.write_min_config(str(out))
        assert "no change" in msg2.lower()

    def test_labels_emitted_for_menus_with_changes(self, tmp_path: Path) -> None:
        """Menu labels appear only for sections containing non-default symbols."""
        kconfig = Kconfig(os.path.join(_KCONFIGS_PATH, "Kconfig.idf_min_config_labels"))
        kconfig.syms["MOTORS_ENABLED"].set_value("y")
        out = tmp_path / "sdkconfig.defaults"
        kconfig.write_min_config(str(out), labels=True)

        contents = out.read_text()
        assert "# Engine" in contents
        assert "# end of Engine" in contents
        assert "Navigation" not in contents

    def test_labels_nested_menus(self, tmp_path: Path) -> None:
        """Nested menu labels are emitted when a symbol in the nested menu changes."""
        kconfig = Kconfig(os.path.join(_KCONFIGS_PATH, "Kconfig.idf_min_config_labels"))
        kconfig.syms["TURBO"].set_value("y")
        out = tmp_path / "sdkconfig.defaults"
        kconfig.write_min_config(str(out), labels=True)

        contents = out.read_text()
        assert "# Engine" in contents
        assert "# Advanced" in contents
        assert "# end of Advanced" in contents
        assert "# end of Engine" in contents
        assert "CONFIG_TURBO=y" in contents

    def test_labels_not_emitted_by_default(self, tmp_path: Path) -> None:
        """Without labels=True, no menu labels are emitted."""
        kconfig = Kconfig(os.path.join(_KCONFIGS_PATH, "Kconfig.idf_min_config_labels"))
        kconfig.syms["MOTORS_ENABLED"].set_value("y")
        out = tmp_path / "sdkconfig.defaults"
        kconfig.write_min_config(str(out))

        contents = out.read_text()
        assert "# Engine" not in contents
        assert "# end of" not in contents
        assert "CONFIG_MOTORS_ENABLED=y" in contents

    def test_labels_stripping_matches_unlabeled(self, tmp_path: Path) -> None:
        """Labeled output, stripped of labels and blanks, equals unlabeled output."""
        kconfig = Kconfig(os.path.join(_KCONFIGS_PATH, "Kconfig.idf_min_config_labels"))
        kconfig.syms["MOTORS_ENABLED"].set_value("y")
        kconfig.syms["TURBO"].set_value("y")
        header = "# test\n"

        out_plain = tmp_path / "plain"
        kconfig.write_min_config(str(out_plain), header=header)
        plain_lines = out_plain.read_text().splitlines(keepends=True)

        out_labeled = tmp_path / "labeled"
        kconfig.write_min_config(str(out_labeled), header=header, labels=True)
        labeled_lines = out_labeled.read_text().splitlines(keepends=True)

        stripped = labeled_lines[:1] + [
            line for line in labeled_lines[1:] if not (line.startswith("#") and line != "# default:\n") and line != "\n"
        ]
        assert stripped == plain_lines
