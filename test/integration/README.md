# Integration Tests

Integration tests verify that esp-idf-kconfig works correctly with ESP-IDF. They require a working ESP-IDF environment.

> **Current scope:** infrastructure only.
> Only one test exists today — a sanity check that runs `idf.py --version`.
> The `cmakev2_*` markers, the `ExampleEntry.build_system` field, and the
> `*_EXAMPLES` tuples are pre-declared scaffolding; concrete example projects,
> the cmakev2 wiring, and the cmakev2 CI jobs are to be added later.
> Anything tagged *(planned)* below does not run yet.

## Prerequisites

1. Clone ESP-IDF and install tools:
   ```bash
   git clone --depth=1 --recurse-submodules --shallow-submodules https://github.com/espressif/esp-idf.git
   cd esp-idf && ./install.sh && source export.sh
   ```

2. Ensure `IDF_PATH` is set and `idf.py` is on `PATH`.

## Running locally

```bash
# Fast integration tests (classic CMake) — currently just the idf.py --version sanity test
pytest test/integration -m fast -v

# Fast integration tests (cmakev2) — runs only the shared sanity test today;
# real cmakev2 coverage is planned for later
pytest test/integration -m cmakev2_fast -v

# Full integration tests (all examples × all supported targets, manual)
# *(planned: empty for now)*
pytest test/integration -m full -v

# Specific parser version only
INTEGRATION_PARSER_VERSIONS=2 pytest test/integration -m fast -v
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
| `-m fast` | **running** — per-MR (automatic on Linux and Windows after unit tests) | classic CMake fast integration tests (currently only the `idf.py --version` sanity test) |
| `-m cmakev2_fast` | *planned* — no CI job yet; selector currently picks up only the shared sanity test | cmakev2 fast integration tests |
| `-m full` | *planned* — manual; no concrete examples yet | classic CMake full integration tests (all examples × all supported targets) |
| `-m cmakev2_full` | *planned* — manual; no concrete examples yet | cmakev2 full integration tests (all examples × all supported targets) |

The concrete example list and cmakev2 selection logic are to be added later.
Until then, `ExampleEntry.build_system` is dead data and `CMAKEV2_*_EXAMPLES`
are empty tuples (see `fixtures/examples.py`).

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
