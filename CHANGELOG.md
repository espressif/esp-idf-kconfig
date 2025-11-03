## v3.3.0 (2025-11-03)

### New Features

- add support for Python 3.14

### Bug Fixes

- fix recursive invalidation logic
- allow nested quotes in prompt string

## v3.2.0 (2025-09-19)

### New Features

- new version of kconfserver
- support deprecated values in expression evaluation

### Bug Fixes

- fix choice related issues during report and sdkconfig loading
- add macro as a valid entry in sourced Kconfig files
- enforce utf-8 encoding in kconfgen
- enhance error message if envvar is misused in source option
- allow internal ESP-IDF envvars to pass kconfcheck
- add a correction of how choice symbols are handled
- use latest value with user-set priority when loading sdkconfig
- support deselected choices in report
- correct handling of choices with default values

## v3.1.1 (2025-08-04)

### Bug Fixes

- **menuconfig**: Allow menuconfig to be directly executed by python

## v3.1.0 (2025-07-28)

### New Features

- **kconfig**: add `set` and `set default` options
- **kconfiglib**: Recognize default value of choice symbols

### Bug Fixes

- rename `kconfiglib` to `esp_kconfiglib`
- do not load promptless symbols from sdkconfig
- move `pyparsing` to core dependencies
- Add `rich` as a missing dependency
- ensure the casing of word Kconfig is "Kconfig"

## v3.0.0 (2025-05-23)

### New Features

- **kconfig**: add Configuration Report
- support simple macros in Kconfig files
- Allow choosing default value if sdkconfig and Kconfig contradict
- **kconfig**: recognize default values in sdkconfig

### Bug Fixes

- **kconfig**: Undefined quoted macros expand to empty string
- **kconfig**: check if default value has correct type
- Correctly parse named choice
- **menuconfig**: Fix saving logic to work with default values
- **kconfig**: print warning when misusing "visible if" option
- **kconfig**: Allow version (X[.Y[.Z]]) as a valid token
- support all entries as choice children in menutree

## v2.5.0 (2025-02-17)

### New Features

- **kconfig**: Allow multiple definition without info statement
- **kconfcheck**: checks for deprecated values in sdkconfig.[ci|defaults]
- **kconfiglib**: parser v2 support of conditional configs inside choice

### Bug Fixes

- allow old names contain lowercase letters in sdkconfig.rename
- **docs**: typo in word orsource (was "oursource")
- Add Python 3.13 as supported version

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
