# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from esp_docs.conf_docs import *  # noqa: F403,F401
from esp_docs.conf_docs import extensions
from esp_docs.conf_docs import html_context

languages = ["en"]
# link roles config
github_repo = "espressif/esp-idf-kconfig"

# context used by sphinx_idf_theme
html_context["github_user"] = "espressif"
html_context["github_repo"] = "esp-idf-kconfig"

html_static_path = ["../_static"]

# Conditional content
extensions += ["esp_docs.esp_extensions.dummy_build_system"]

# Extra options required by sphinx_idf_theme
project_slug = "esp-idf-kconfig"

versions_url = "./_static/esp_idf_kconfig_versions.js"
