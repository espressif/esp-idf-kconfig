## v2.4.1 (2024-12-10)

### Bug Fixes

- Prevent multidefinition warning when Kconfig sourced multiple times

## v2.4.0 (2024-11-29)

### New Features

- **kconfiglib**: Check duplicate symbol definitions
- add sdkconfig.rename checker
- **kconfcheck**: Add in-place suggestions when running as precommit hook
- **kconfiglib**: Add new parser based on pyparsing

### Bug Fixes

- Do not try to remove file.new in replace mode
- do not return from finally blocks
- **kconfiglib**: Fix order of env_var and config name in warning

### Code Refactoring

- remove TRISTATE type, m value and module logic
- Move docstring to the attributes they are documenting
- Set class attributes during initialization
- Change string formatting, remove Py2 support
- Increase line len to 120

### Performance Improvements

- **kconfiglib**: Enhance performance by manually parsing option blocks

## v2.3.0 (2024-07-30)

### New Features

- **kconfcheck**: add check whether symbol name is all uppercase
- **kconfgen**: Support renames with inversion in sdkconfig.renames

### Bug Fixes

- **kconfgen**: Improve error message for int/hex without default
- **kconfgen**: Disallow rename to the same name in sdkconfig.renames
- Dont ask for the filename when saving configuration

### Code Refactoring

- **kconfgen**: Improve code quality of kconfgen.py

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
