# Integration Tests

Integration tests verify that esp-idf-kconfig works correctly with ESP-IDF. They require a working ESP-IDF environment.

## Prerequisites

1. Clone ESP-IDF and install tools:
   ```bash
   git clone --depth=1 --recurse-submodules --shallow-submodules https://github.com/espressif/esp-idf.git
   cd esp-idf && ./install.sh && source export.sh
   ```

2. Ensure `IDF_PATH` is set and `idf.py` is on `PATH`.

## Running locally

```bash
# Fast integration tests (classic CMake)
pytest test/integration -m fast -v

# Fast integration tests (cmakev2)
pytest test/integration -m cmakev2_fast -v

# Specific parser version only
INTEGRATION_PARSER_VERSIONS=2 pytest test/integration -m fast -v

# Run only build tests
pytest test/integration/test_build.py -v
```

## Environment variables

| Variable | Description |
|---|---|
| `IDF_PATH` | **Required.** Path to an ESP-IDF checkout with tools installed. |
| `KCONFIG_PARSER_VERSION` | Set by test parametrisation (`1` or `2`). |
| `INTEGRATION_PARSER_VERSIONS` | Override parser versions to test (comma-separated, e.g. `1,2`). |
| `MENUCONFIG_HEADLESS` | Set to `1` to skip the TUI in `python -m esp_menuconfig`. |

## Sharding (CI)

Sharding is driven by the `INTEGRATION_SHARD_TOTAL` / `INTEGRATION_SHARD_INDEX`
environment variables (0-based index).  We use dedicated env vars instead of
GitLab's `CI_NODE_TOTAL`/`CI_NODE_INDEX` because GitLab sets those for
`parallel: matrix:` too, which would incorrectly split tests across matrix
cells that only differ in `IDF_BRANCH`.

## Test markers

| Marker | Status | Description |
|---|---|---|
| `-m fast` | **running** — per-MR (automatic on Linux and Windows after unit tests) | classic CMake fast integration tests |
| `-m cmakev2_fast` | **running** — same as `fast` | cmakev2 fast integration tests |
| `-m full` | *planned* — manual; concrete examples to be populated later | classic CMake full integration tests (all examples × all supported targets) |
| `-m cmakev2_full` | *planned* — manual; concrete examples to be populated in later | cmakev2 full integration tests (all examples × all supported targets) |


## CI platforms

| Job | Runner / shell | IDF branches | Trigger | Status |
|---|---|---|---|---|
| `integration_fast` | `build, internet` (Docker, Linux) / bash | `master` | automatic per-MR (after unit tests succeed) | **running** |
| `integration_fast_compat` | `build, internet` (Docker, Linux) / bash | `release/v6.0`, `release/v6.1` | manual | **running** |
| `integration_fast_windows` | `windows-vm`, `brew` (shell executor) / PowerShell | `master` | automatic per-MR (after unit tests succeed) | **running** |
| `integration_fast_windows_compat` | `windows-vm`, `brew` (shell executor) / PowerShell | `release/v6.0`, `release/v6.1` | manual | **running** |
| `integration_cmakev2_fast` and `integration_cmakev2_fast_windows` | — | — | — | *planned* |

`master` runs automatically on every MR to catch regressions early. Compatibility runs against IDF release branches are manual: this avoids saturating the small `windows-vm` runner pool while still keeping the option to verify older IDF revisions before merging.

All running jobs use `allow_failure: true` while the integration suite stabilises; flip the templates' `allow_failure` once the runs are reliable.

### How the integration jobs are wired up

The CI `before_script` installs ESP-IDF first (`./install.{sh,ps1}`), sources `export.{sh,ps1}`, and then `pip install -e .[dev]`s esp-idf-kconfig **into IDF's active Python venv**. Pytest therefore runs from inside IDF's venv, so `sys.executable` already has `click` and the other IDF Python dependencies needed by `idf.py`. There is no separate `venv\` for the test runner.

Integration jobs run `pytest` directly (no `coverage run`). `idf.py` spawns many Python subprocesses and the `coverage[toml]` `.pth` startup hook proved fragile across cwds and platforms; coverage is collected by the unit-test suites instead.
