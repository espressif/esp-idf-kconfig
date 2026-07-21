#!/usr/bin/env python
# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import io
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

import pytest

import esp_kconfiglib.core as kconfiglib
from esp_idf_kconfig import gen_kconfig_doc


@dataclass
class Data:
    target: Optional[str] = None
    config: Optional[kconfiglib.Kconfig] = None
    visibility: Optional[gen_kconfig_doc.ConfigTargetVisibility] = None
    reverse_deps: Optional[tuple] = None


@pytest.fixture(scope="class")
def data():
    return Data()


@pytest.mark.parametrize("prepare", (1, 2), indirect=True)
class TestDocOutput:
    @pytest.fixture(scope="class", autouse=True)
    def prepare(_, data, request):
        os.environ["IDF_TARGET"] = "chipa"
        data.target = os.environ["IDF_TARGET"]
        data.config = kconfiglib.Kconfig("Kconfig", parser_version=request.param)
        data.visibility = gen_kconfig_doc.ConfigTargetVisibility(data.config, data.target)
        data.reverse_deps = gen_kconfig_doc._cache_reverse_dependency_mappings(data.config)

    def get_config(self, name, data):
        sym = data.config.syms.get(name)
        if sym:
            return sym.nodes[0]
        choice = data.config.named_choices.get(name)
        if choice:
            return choice.nodes[0]
        raise RuntimeError("Unimplemented {}".format(name))

    def get_doc_out(self, config_name, data):
        with io.StringIO() if sys.version_info.major == 3 else io.BytesIO() as output:
            gen_kconfig_doc.write_menu_item(
                output,
                self.get_config(config_name, data),
                data.visibility,
                data.config,
                data.reverse_deps,
            )
            output.seek(0)
            return output.read()

    def test_simple_default(self, data):
        s = self.get_doc_out("EXT_CONFIG3_FOR_CHIPA_MENU", data)
        assert "- 5" in s

    def test_multiple_defaults(self, data):
        s = self.get_doc_out("CHIPA_OPTION", data)
        # Generic conditions are kept (not evaluated away from current values).
        # Promptless CHIPA_REV_MIN has no docs anchor → plain CONFIG_ name.
        assert "- 5 if CONFIG_CHIPA_REV_MIN < 2" in s
        assert "- 4 if CHIPA_VERSION = 2" in s
        assert "- 9 if CONFIG_CHIPA_REV_MIN = 3" in s

    def test_string_default(self, data):
        s = self.get_doc_out("COMPILER", data)
        assert "- ca" in s
        assert "- cb" not in s

    def test_bool_default(self, data):
        s = self.get_doc_out("BOOL_OPTION", data)
        assert "- Yes" in s

    def test_bool_default_dependency(self, data):
        # A symbol-valued default (default BOOL_OPTION) links to that symbol
        # instead of freezing its current value.
        s = self.get_doc_out("BOOL_OPTION2", data)
        assert "- :ref:`CONFIG_BOOL_OPTION`" in s

    def test_hex_default(self, data):
        s = self.get_doc_out("HEX_OPTION", data)
        assert '- "0xce"' in s
        assert '- "0xff"' not in s

    def test_hex_range(self, data):
        s = self.get_doc_out("HEX_OPTION", data)
        assert "- from 0xf to 0xce" in s
        assert "- from 0xfe" not in s

    def test_int_range(self, data):
        s = self.get_doc_out("INT_OPTION", data)
        assert "- from 1 to 10" in s
        assert "- from 100" not in s

    def test_choice(self, data):
        s = self.get_doc_out("CHOICE_FOR_CHIPA", data)
        assert "Available options:" in s
        assert re.search(r"- op1\s+\(CONFIG_CHOICE_FOR_CHIPA_OP1\)", s)
        assert re.search(r"- op2\s+\(CONFIG_CHOICE_FOR_CHIPA_OP2\)", s)

        s = self.get_doc_out("OPT_DEPENDENT_ON_CHOICE_OP2", data)
        assert "- Yes (enabled) if :ref:`CONFIG_CHOICE_FOR_CHIPA_OP2<CONFIG_CHOICE_FOR_CHIPA_OP2>`" in s

    def test_can_be_set_when_combines_prompt_and_depends(self, data):
        s = self.get_doc_out("DEP_COND_PROMPT", data)
        assert "Symbol can be set when:" in s
        assert ":ref:`CONFIG_DEP_GATE`" in s
        assert ":ref:`CONFIG_BOOL_OPTION`" in s
        # always-assignable options omit the section
        s = self.get_doc_out("ALWAYS_VISIBLE", data)
        assert "Symbol can be set when:" not in s

    def test_when_enabled_forward_dependencies(self, data):
        s = self.get_doc_out("DEP_SOURCE", data)
        assert "Symbol can be set when:" in s
        assert ":ref:`CONFIG_DEP_GATE`" in s
        assert "This symbol affects the value of following symbols:" in s
        assert "- forcefully enables :ref:`CONFIG_DEP_SELECTED`" in s
        assert "- sets :ref:`CONFIG_DEP_SET_TARGET` to 42 if :ref:`CONFIG_BOOL_OPTION`" in s
        # imply / set default are not documented (weak; overridden by sdkconfig.defaults)
        assert "enables :ref:`CONFIG_DEP_IMPLIED`" not in s
        assert "Sets default value" not in s
        assert "implies" not in s
        # source depends on is not repeated on unconditional select
        assert "forcefully enables :ref:`CONFIG_DEP_SELECTED` if" not in s

    def test_forced_by_strong_reverse_only(self, data):
        s = self.get_doc_out("DEP_SELECTED", data)
        assert "Following symbols affect the value of this symbol:" in s
        assert "- forcefully enabled by :ref:`CONFIG_DEP_SOURCE`" in s
        assert "implied by" not in s

        s = self.get_doc_out("DEP_SET_TARGET", data)
        assert "Following symbols affect the value of this symbol:" in s
        assert "- set by :ref:`CONFIG_DEP_SOURCE` to 42 if :ref:`CONFIG_BOOL_OPTION`" in s
        assert "weakly set by" not in s

        s = self.get_doc_out("DEP_IMPLIED", data)
        assert "Following symbols affect the value of this symbol:" not in s
        assert "implied by" not in s

    def test_promptless_symbols_without_ref(self, data):
        s = self.get_doc_out("DEP_SELECTS_PROMPTLESS", data)
        assert "This symbol affects the value of following symbols:" in s
        assert "- forcefully enables CONFIG_DEP_PROMPTLESS_TARGET" in s
        assert ":ref:`CONFIG_DEP_PROMPTLESS_TARGET`" not in s

    def test_forced_by_skips_inactive_target_sources(self, data):
        # chipa: only IDF_TARGET_CHIPA applies; promptless source → plain name, no :ref:
        s = self.get_doc_out("DEP_FORCED_BY_TARGET", data)
        assert "Following symbols affect the value of this symbol:" in s
        assert "- forcefully enabled by CONFIG_IDF_TARGET_CHIPA" in s
        assert ":ref:`CONFIG_IDF_TARGET_CHIPA`" not in s
        assert "CONFIG_IDF_TARGET_CHIPB" not in s

    def test_target_specific_range_default_shadows_fallback(self, data):
        s = self.get_doc_out("TARGETED_RANGE_DEFAULT", data)
        assert "Symbol can be set when:" in s
        assert ":ref:`CONFIG_BOOL_OPTION`" in s
        assert "- from 1 to 32" in s
        assert "- from 1 to 16" not in s
        assert "- from 1 to 4" not in s
        assert "- 32" in s
        assert "- 16" not in s
        assert "- 4" not in s
        # depends on already in Can be set when — not repeated on the active entry
        assert "from 1 to 32 if" not in s
        assert "- 32 if" not in s

    def test_generic_default_keeps_condition_and_fallback(self, data):
        s = self.get_doc_out("GENERIC_DEFAULT_IF", data)
        assert "- 7 if :ref:`CONFIG_DEP_GATE`" in s
        assert "- 3" in s
        assert "- 3 if" not in s
