#!/usr/bin/env python
# SPDX-FileCopyrightText: 2024-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import io
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

import pytest

import kconfiglib.core as kconfiglib
from esp_idf_kconfig import gen_kconfig_doc


@dataclass
class Data:
    target: Optional[str] = None
    config: Optional[kconfiglib.Kconfig] = None
    visibility: Optional[gen_kconfig_doc.ConfigTargetVisibility] = None


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
            gen_kconfig_doc.write_menu_item(output, self.get_config(config_name, data), data.visibility)
            output.seek(0)
            return output.read()

    def test_simple_default(self, data):
        s = self.get_doc_out("EXT_CONFIG3_FOR_CHIPA_MENU", data)
        assert "- 5" in s

    def test_multiple_defaults(self, data):
        s = self.get_doc_out("CHIPA_OPTION", data)
        assert "- 5" not in s
        assert "- 4 if CHIPA_VERSION = 2" in s
        assert "- 9" not in s

    def test_string_default(self, data):
        s = self.get_doc_out("COMPILER", data)
        assert "- ca" in s
        assert "- cb" not in s

    def test_bool_default(self, data):
        s = self.get_doc_out("BOOL_OPTION", data)
        assert "- Yes" in s

    def test_bool_default_dependency(self, data):
        s = self.get_doc_out("BOOL_OPTION2", data)
        assert "- Yes" in s

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
