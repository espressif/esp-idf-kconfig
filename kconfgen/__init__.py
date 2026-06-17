# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import sys

from esp_pylib.logger import log

# Keep stdout reserved for machine output
log.set_info_stream(sys.stderr)
