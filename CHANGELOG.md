## v2.2.0 (2024-03-15)

### New Features

- **kconfiglib**: Remove kconfiglib as a dependency a make it modules

### Bug Fixes

- **menuconfig**: fix menuconfig incompatibility on Win, Python 3.12

## v2.1.0 (2024-01-26)

### New Features

- **kconfcheck**: Added kconfcheck package to pre-commit hook

## v2.0.2 (2024-01-12)

### Bug Fixes

- **kconfcheck**: Fixed false-positive indent errors and extended limits

## v2.0.1 (2023-11-09)

### Bug Fixes

- **docs**: fix not expression evaluation for range parameter

## v2.0.0 (2023-10-20)

### Bug Fixes

- change logic for ESP_IDF_KCONFIG_MIN_LABELS from is set to "1"

## v1.4.0 (2023-10-20)

### New Features

- menu labels in min config
- **doc**: generate hyperlink targets for choices
- **min_config**: convert CONFIG_XY is not set to CONFIG_XY=n

### Bug Fixes

- add execute permissions for kconfcheck tests
- remove unnecessary requirements
