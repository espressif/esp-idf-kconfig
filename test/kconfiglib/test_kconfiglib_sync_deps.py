# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import time

import pytest

from esp_kconfiglib import Kconfig


def _write_kconfig(path):
    with open(path, "w", encoding="utf-8") as kconfig_file:
        kconfig_file.write(
            "\n".join(
                [
                    'mainmenu "Test"',
                    "",
                    "config FOO",
                    '    bool "Foo"',
                    "    default y",
                    "",
                    "config BAR",
                    '    bool "Bar"',
                    "",
                    "config BAZ",
                    '    string "Baz"',
                    '    default "hi"',
                    "",
                ]
            )
        )


@pytest.fixture()
def version(request):
    version = request.param
    os.environ["KCONFIG_PARSER_VERSION"] = version
    yield
    del os.environ["KCONFIG_PARSER_VERSION"]


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
def test_sync_deps_tracks_changed_symbols(tmp_path, version):
    # Verify sync_deps only touches files for symbols whose values change.
    kconfig_path = os.path.join(str(tmp_path), "Kconfig")
    _write_kconfig(kconfig_path)
    kconf = Kconfig(kconfig_path)

    deps_path = os.path.join(str(tmp_path), "deps")
    kconf.sync_deps(deps_path)

    auto_conf_path = os.path.join(deps_path, "auto.conf")
    with open(auto_conf_path, "r", encoding="utf-8") as auto_conf_file:
        auto_conf = auto_conf_file.read()
    assert "CONFIG_FOO=y\n" in auto_conf
    assert 'CONFIG_BAZ="hi"\n' in auto_conf
    assert "CONFIG_BAR" not in auto_conf

    foo_path = os.path.join(deps_path, "foo.cdep")
    bar_path = os.path.join(deps_path, "bar.cdep")
    baz_path = os.path.join(deps_path, "baz.cdep")

    assert os.path.exists(foo_path)
    assert os.path.exists(baz_path)
    # n symbols do not have a header file
    assert not os.path.exists(bar_path)

    foo_mtime = os.stat(foo_path).st_mtime
    baz_mtime = os.stat(baz_path).st_mtime

    time.sleep(1.1)  # sleep to ensure mtime changes

    kconf.syms["BAR"].set_value("y")
    kconf.syms["BAZ"].set_value("world")
    kconf.sync_deps(deps_path)

    assert os.path.exists(bar_path)
    assert os.stat(foo_path).st_mtime == foo_mtime
    assert os.stat(baz_path).st_mtime > baz_mtime

    with open(auto_conf_path, "r", encoding="utf-8") as auto_conf_file:
        updated_auto_conf = auto_conf_file.read()
    assert "CONFIG_FOO=y\n" in updated_auto_conf
    assert "CONFIG_BAR=y\n" in updated_auto_conf
    assert 'CONFIG_BAZ="world"\n' in updated_auto_conf
