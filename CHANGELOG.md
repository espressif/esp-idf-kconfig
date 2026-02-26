<a href="https://www.espressif.com">
    <img src="https://www.espressif.com/sites/all/themes/espressif/logo-black.svg" align="right" height="20" />
</a>

# CHANGELOG

> All notable changes to this project are documented in this file.
> This list is not exhaustive - only important changes, fixes, and new features in the code are reflected here.

<div align="center">
    <a href="https://keepachangelog.com/en/1.1.0/">
        <img alt="Static Badge" src="https://img.shields.io/badge/Keep%20a%20Changelog-v1.1.0-salmon?logo=keepachangelog&logoColor=black&labelColor=white&link=https%3A%2F%2Fkeepachangelog.com%2Fen%2F1.1.0%2F">
    </a>
    <a href="https://www.conventionalcommits.org/en/v1.0.0/">
        <img alt="Static Badge" src="https://img.shields.io/badge/Conventional%20Commits-v1.0.0-pink?logo=conventionalcommits&logoColor=black&labelColor=white&link=https%3A%2F%2Fwww.conventionalcommits.org%2Fen%2Fv1.0.0%2F">
    </a>
    <a href="https://semver.org/spec/v2.0.0.html">
        <img alt="Static Badge" src="https://img.shields.io/badge/Semantic%20Versioning-v2.0.0-grey?logo=semanticrelease&logoColor=black&labelColor=white&link=https%3A%2F%2Fsemver.org%2Fspec%2Fv2.0.0.html">
    </a>
</div>
<hr>

## v3.5.0 (2026-02-25)

### ✨ New Features

- introduce float type *(Jan Beran - f1d6615)*

### 🐛 Bug Fixes

- **menuconfig**: compare changes against main sdkconfig *(Jan Beran - 2d49295)*
- gracefully exit from menuconfig after SIGINT *(Jan Beran - 93d62bc)*
- menuconfig returns exit message on Windows *(Jan Beran - aed6274)*
- respect dependencies when loading default values *(Jan Beran - 0ee53b1)*

### 📖 Documentation

- provide example how to solve default value mismatch *(Jan Beran - 6ad9183)*


## v3.4.2 (2026-01-12)

### 🐛 Bug Fixes

- remove IndetedBlock from the new parser *(Jan Beran - 2ceb8d0)*
- load user-set symbols at once for each choice *(Jan Beran - 173f999)*
- update code to comply with pyparsing 3.3.1 *(Jan Beran - f6889fd)*
- ensure ignore pragmas are working *(Jan Beran - 92d8ff3)*


## v3.4.1 (2025-12-10)

### 🐛 Bug Fixes

- init Symbol._default_value_injected to prevent menuconfig crashing *(Jan Beran - b304093)*


## v3.4.0 (2025-12-04)

### ✨ New Features

- report if sdkconfig.defaults tries to set disabled symbol/choice *(Jan Beran - e7c0a56)*
- add "warning" option to mark dangerous config options *(Jan Beran - 21a3233)*

### 🐛 Bug Fixes

- ensure default values are immediately available after injection *(Jan Beran - a99e064)*
- use the right bool value form in Symbol.set_value() *(Jan Beran - 1aec9d8)*
- correctly reset value_is_default flag *(Jan Beran - f121fed)*
- Omit not included component configuration in .rst docs *(Jan Beran - 6d41ba9)*


## v3.3.0 (2025-11-03)

### ✨ New Features

- add support for Python 3.14 *(Jan Beran - dde2b7e)*

### 🐛 Bug Fixes

- fix recursive invalidation logic *(Jan Beran - 321688f)*
- allow nested quotes in prompt string *(Jan Beran - 14473c3)*

---

## v3.2.0 (2025-09-19)

### ✨ New Features

- new version of kconfserver *(Jan Beran - 20df5c8)*
- support deprecated values in expression evaluation *(Jan Beran - bb4fc8a)*

### 🐛 Bug Fixes

- fix choice related issues during report and sdkconfig loading *(Jan Beran - a6cf1b9)*
- add macro as a valid entry in sourced Kconfig files *(Jan Beran - 24996ee)*
- enforce utf-8 encoding in kconfgen *(Jan Beran - d2673c9)*
- enhance error message if envvar is misused in source option *(Jan Beran - 34c0a8c)*
- allow internal ESP-IDF envvars to pass kconfcheck *(Jan Beran - 031bafc)*
- add a correction of how choice symbols are handled *(Jan Beran - 36d60f8)*
- use latest value with user-set priority when loading sdkconfig *(Jan Beran - 31fc96a)*
- support deselected choices in report *(Jan Beran - 3981a04)*
- correct handling of choices with default values *(Jan Beran - 78e7e52)*

---

## v3.1.1 (2025-08-04)

### 🐛 Bug Fixes

- **menuconfig**: Allow menuconfig to be directly executed by python *(Jan Beran - fd7e004)*

### 📖 Documentation

- add migration guide with current changes *(Jan Beran - dc83106)*
- fix Kconfig grammar, edit differences between parsers *(Jan Beran - 3445d6f)*
- describe how to use kconfcheck and its pre-commit hook *(Jan Beran - a7b6389)*

---

## v3.1.0 (2025-07-28)

### ✨ New Features

- **kconfig**: add `set` and `set default` options *(Jan Beran - 3e421dd)*
- **kconfiglib**: Recognize default value of choice symbols *(Jan Beran - 2f1aa84)*

### 🐛 Bug Fixes

- rename `kconfiglib` to `esp_kconfiglib` *(Jan Beran - 817a0f9)*
- do not load promptless symbols from sdkconfig *(Jan Beran - a951644)*
- move `pyparsing` to core dependencies *(Jan Beran - f680b3a)*
- Add `rich` as a missing dependency *(ysard - bc31f5e)*
- ensure the casing of word Kconfig is "Kconfig" *(Jan Beran - 4a9f17e)*

---

## v3.0.0 (2025-05-23)

### ✨ New Features

- **kconfig**: add Configuration Report *(Jan Beran - 06e0d28)*
- **kconfig**: recognize default values in sdkconfig *(Jan Beran - 39a7cdb)*
- support simple macros in Kconfig files *(Jan Beran - b349b73)*
- Allow choosing default value if sdkconfig and Kconfig contradict *(Jan Beran - 9e6a192)*

### 🐛 Bug Fixes

- **kconfig**: Undefined quoted macros expand to empty string *(Jan Beran - 84b1ce0)*
- **kconfig**: check if default value has correct type *(Jan Beran - a932dfd)*
- **menuconfig**: Fix saving logic to work with default values *(Jan Beran - 01e79b4)*
- **kconfig**: print warning when misusing "visible if" option *(Jan Beran - d64637b)*
- **kconfig**: Allow version (X[.Y[.Z]]) as a valid token *(Jan Beran - 88e70eb)*
- Correctly parse named choice *(Jan Beran - d230c56)*
- support all entries as choice children in menutree *(Jan Beran - f95a98a)*

### 📖 Documentation

- **kconfserver**: Add initial kconfserver documentation *(Jan Beran - b3944bd)*

---

## v2.5.0 (2025-02-17)

### ✨ New Features

- **kconfig**: Allow multiple definition without info statement *(Jan Beran - 4963458)*
- **kconfcheck**: checks for deprecated values in sdkconfig.[ci|defaults] *(Jan Beran - 159b27d)*
- **kconfiglib**: parser v2 support of conditional configs inside choice *(Jan Beran - 8f6819d)*

### 🐛 Bug Fixes

- **docs**: typo in word orsource (was "oursource") *(Jan Beran - c847929)*
- allow old names contain lowercase letters in sdkconfig.rename *(Jan Beran - d397877)*
- Add Python 3.13 as supported version *(Jan Beran - 058611f)*

---

## v2.4.1 (2024-12-10)

### ✨ New Features

- **kconfiglib**: Check duplicate symbol definitions *(Jan Beran - cbae2b8)*
- **kconfcheck**: Add in-place suggestions when running as precommit hook *(Jan Beran - b2cfdb7)*
- **kconfiglib**: Add new parser based on pyparsing *(Jan Beran - 88ab56b)*
- add sdkconfig.rename checker *(Jan Beran - 0de5129)*

### 🐛 Bug Fixes

- **kconfiglib**: Fix order of env_var and config name in warning *(Jan Beran - 893d1a6)*
- Prevent multidefinition warning when Kconfig sourced multiple times *(Jan Beran - 47c1fa6)*
- Do not try to remove file.new in replace mode *(Jan Beran - bd8aa4c)*
- do not return from finally blocks *(Jan Beran - 6442bec)*

### 📖 Documentation

- Add initial documentation of kconfiglib and allow CI docs build *(Jan Beran - c3de861)*

### 🔧 Code Refactoring

- remove TRISTATE type, m value and module logic *(Jan Beran - d1a9672)*
- Move docstring to the attributes they are documenting *(Jan Beran - a063b13)*
- Set class attributes during initialization *(Jan Beran - aaf88c7)*
- Change string formatting, remove Py2 support *(Jan Beran - 320a188)*
- Increase line len to 120 *(Jan Beran - b0086a6)*

---

## v2.3.0 (2024-07-30)

### ✨ New Features

- **kconfcheck**: add check whether symbol name is all uppercase *(Jan Beran - 57f21d4)*
- **kconfgen**: Support renames with inversion in sdkconfig.renames *(Jan Beran - a3489f4)*

### 🐛 Bug Fixes

- **kconfgen**: Improve error message for int/hex without default *(Jan Beran - c52466e)*
- **kconfgen**: Disallow rename to the same name in sdkconfig.renames *(Jan Beran - 04d8484)*
- Dont ask for the filename when saving configuration *(Jan Beran - 57d9b34)*

### 🔧 Code Refactoring

- **kconfgen**: Improve code quality of kconfgen.py *(Jan Beran - aa9c78d)*

---

## v2.2.0 (2024-03-15)

### ✨ New Features

- **kconfiglib**: Remove kconfiglib as a dependency a make it modules *(Jan Beran - bb321e3)*

### 🐛 Bug Fixes

- **menuconfig**: fix menuconfig incompatibility on Win, Python 3.12 *(Jan Beran - 0fdc8b0)*

---

## v2.1.0 (2024-01-26)

### ✨ New Features

- **kconfcheck**: Added kconfcheck package to pre-commit hook *(Jakub Kocka - 869cd65)*

---

## v2.0.2 (2024-01-12)

### 🐛 Bug Fixes

- **kconfcheck**: Fixed false-positive indent errors and extended limits *(Jakub Kocka - 004cccf)*

---

## v2.0.1 (2023-11-09)

### 🐛 Bug Fixes

- **docs**: fix not expression evaluation for range parameter *(Peter Dragun - e148181)*

---

## v2.0.0 (2023-10-20)

### 🐛 Bug Fixes

- change logic for ESP_IDF_KCONFIG_MIN_LABELS from is set to "1" *(Peter Dragun - 4ca7384)*

---

## v1.4.0 (2023-10-20)

### ✨ New Features

- **doc**: generate hyperlink targets for choices *(Ivan Grokhotkov - 5688e60)*
- **min_config**: convert CONFIG_XY is not set to CONFIG_XY=n *(Peter Dragun - ef49886)*
- menu labels in min config *(Peter Dragun - 7087add)*

### 🐛 Bug Fixes

- add execute permissions for kconfcheck tests *(Peter Dragun - 963e41a)*
- remove unnecessary requirements *(Peter Dragun - a3d1ae3)*

### 📖 Documentation

- Kconfig formatting rules and backward compatibility of options *(Roland Dobai - 4304c66)*
- Copy CMake docs to a separate set of directories *(Angus Gratton - 6889aee)*

---

<div align="center">
    <small>
        <b>
            <a href="https://www.github.com/espressif/cz-plugin-espressif">Commitizen Espressif plugin</a>
        </b>
    <br>
        <sup><a href="https://www.espressif.com">Espressif Systems CO LTD. (2025)</a><sup>
    </small>
</div>
