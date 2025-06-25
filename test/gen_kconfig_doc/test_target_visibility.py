#!/usr/bin/env python
# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

import esp_kconfiglib.core as kconfiglib
from esp_idf_kconfig import gen_kconfig_doc


class ConfigTargetVisibilityTestCase:
    @pytest.fixture(autouse=True)
    def setup_class(self, request):
        self.parser_version = request.param
        self.target = os.environ["IDF_TARGET"]
        self.config = kconfiglib.Kconfig("Kconfig", parser_version=self.parser_version)
        self.v = gen_kconfig_doc.ConfigTargetVisibility(self.config, self.target)

    def _get_config(self, name):
        sym = self.config.syms.get(name)
        if sym and len(sym.nodes) > 0:
            return sym.nodes[0]
        choice = self.config.named_choices.get(name)
        if choice:
            return choice.nodes[0]
        raise RuntimeError("Unimplemented {}".format(name))

    def visible(self, config_name):
        assert self.v.visible(self._get_config(config_name))

    def invisible(self, config_name):
        assert not self.v.visible(self._get_config(config_name))


@pytest.mark.parametrize("setup_class", [1, 2], indirect=True)
class TestConfigTargetVisibilityChipA(ConfigTargetVisibilityTestCase):
    @pytest.fixture(scope="class", autouse=True)
    def setup_chip(self):
        os.environ["IDF_TARGET"] = "chipa"

    def test_config_visibility(self):
        assert os.environ.get("IDF_TARGET") == "chipa"
        assert self.parser_version == self.config.parser_version

        self.invisible("IDF_TARGET")
        self.invisible("IDF_TARGET_CHIPA")
        self.visible("ALWAYS_VISIBLE")
        self.visible("ALWAYS_VISIBLE_CHOICE")
        self.visible("CONFIG_FOR_CHIPA")
        self.invisible("CONFIG_FOR_CHIPB")
        self.visible("CHOICE_FOR_CHIPA")
        self.invisible("CHOICE_FOR_CHIPB")
        self.visible("EXT_CONFIG1_FOR_CHIPA_MENU")
        self.visible("EXT_CONFIG2_FOR_CHIPA_MENU")
        self.visible("EXT_CONFIG3_FOR_CHIPA")
        self.invisible("EXT_CONFIG1_FOR_CHIPB_MENU")
        self.invisible("EXT_CONFIG2_FOR_CHIPB_MENU")
        self.invisible("EXT_CONFIG3_FOR_CHIPB")
        self.visible("EXT_CONFIG4")
        self.visible("DEEP_DEPENDENT_CONFIG")
        self.visible("DEEP_DEPENDENT_CONFIG_INV")
        self.visible("DEEP_DEPENDENT_CHOICE")
        self.invisible("INVISIBLE1")
        self.visible("VISIBLE1")
        self.visible("CONFIG_FOR_CHIPA_DEPENDS_VAR1")
        self.visible("CONFIG_FOR_CHIPA_DEPENDS_VAR2")
        self.visible("CONFIG_FOR_CHIPA_DEPENDS_VAR3")
        self.visible("CONFIG_DEPENDS_ENV_VAR1")
        self.visible("CONFIG_DEPENDS_ENV_VAR2")
        self.visible("CHIPA_VERSION")
        self.invisible("CHIPA_REV_MIN")
        self.visible("CHIPA_FEATURE_FROM_V1")
        self.visible("CHIPA_FEATURE_FROM_V3")


@pytest.mark.parametrize("setup_class", [1, 2], indirect=True)
class TestConfigTargetVisibilityChipB(ConfigTargetVisibilityTestCase):
    @pytest.fixture(scope="class", autouse=True)
    def setup_chip(self):
        os.environ["IDF_TARGET"] = "chipb"

    def test_config_visibility(self):
        assert os.environ.get("IDF_TARGET") == "chipb"
        assert self.parser_version == self.config.parser_version

        self.invisible("IDF_TARGET")
        self.invisible("IDF_TARGET_CHIPA")
        self.visible("ALWAYS_VISIBLE")
        self.visible("ALWAYS_VISIBLE_CHOICE")
        self.invisible("CONFIG_FOR_CHIPA")
        self.visible("CONFIG_FOR_CHIPB")
        self.invisible("CHOICE_FOR_CHIPA")
        self.visible("CHOICE_FOR_CHIPB")
        self.invisible("EXT_CONFIG1_FOR_CHIPA_MENU")
        self.invisible("EXT_CONFIG2_FOR_CHIPA_MENU")
        self.invisible("EXT_CONFIG3_FOR_CHIPA")
        self.visible("EXT_CONFIG1_FOR_CHIPB_MENU")
        self.visible("EXT_CONFIG2_FOR_CHIPB_MENU")
        self.visible("EXT_CONFIG3_FOR_CHIPB")
        self.visible("EXT_CONFIG4")
        self.invisible("DEEP_DEPENDENT_CONFIG")
        self.visible("DEEP_DEPENDENT_CONFIG_INV")
        self.invisible("DEEP_DEPENDENT_CHOICE")
        self.invisible("INVISIBLE1")
        self.visible("VISIBLE1")
        self.invisible("CONFIG_FOR_CHIPA_DEPENDS_VAR1")
        self.invisible("CONFIG_FOR_CHIPA_DEPENDS_VAR2")
        self.invisible("CONFIG_FOR_CHIPA_DEPENDS_VAR3")
        self.visible("CONFIG_DEPENDS_ENV_VAR1")
        self.visible("CONFIG_DEPENDS_ENV_VAR2")
        self.invisible("CHIPA_VERSION")
        self.invisible("CHIPA_REV_MIN")
        self.invisible("CHIPA_FEATURE_FROM_V1")
        self.invisible("CHIPA_FEATURE_FROM_V3")
