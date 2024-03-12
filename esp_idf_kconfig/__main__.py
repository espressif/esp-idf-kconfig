# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
print("ESP-IDF Kconfig tool")
msg = "Please select a tool to run with command:"
print(
    f"{msg}"
    f"\n{' '*int(len(msg)/2)}"
    f"Kconfig file checker. {' '*8} (python -m kconfcheck)"
    f"\n{' '*int(len(msg)/2)}"
    "Run JSON configuration server. (idf.py confserver or python -m kconfserver)"
    f"\n{' '*int(len(msg)/2)}"
    f"Config Generation Tool. {' '*6} (python -m kconfgen)"
)
