# Agent context: esp-idf-kconfig

This repo is part of the [ESP-IDF](https://github.com/espressif/esp-idf) SDK. It provides Kconfig parsing, IDE support (e.g. kconfserver), configuration reports, and documentation generation for the Kconfig language ([kernel kconfig-language](https://www.kernel.org/doc/Documentation/kbuild/kconfig-language.txt)).

## Repo layout

- **`esp_kconfiglib/`** — Core Kconfig library (parsing, evaluation, config load/save). Main logic lives here.
- **`kconfserver/`** — Language/server for IDE support (LSP-style).
- **`menuconfig/`** — TUI menuconfig implementation.
- **`kconfcheck/`** — Checks and suggestions for sdkconfig / Kconfig.
- **`kconfgen/`** — Config generation utilities.
- **`kcompare/`** — Compare Kconfig between two ESP-IDF commits (repo mode).
- **`esp_idf_kconfig/`** — Package entry point (`__main__.py`).
- **`test/`** — Tests per component (kconfiglib, kconfserver, menuconfig, gen_kconfig_doc, kconfcheck, kcompare).
- **`docs/`** — Sphinx docs (e.g. `docs/en/`). It also uses [esp-docs](https://github.com/espressif/esp-docs) as an Espressif specific extension of Sphinx.

## esp_kconfiglib (main analysis target)

The central module is **`esp_kconfiglib/core.py`** (~8.1k lines). Prefer **semantic search by concept** and **targeted reads with line ranges**; avoid loading the whole file.

### core.py — class and section map

| Class / area        | Approx. lines | Role |
|---------------------|---------------|------|
| `Kconfig`           | 444–4072      | Top-level API: load Kconfig file, load sdkconfig file, load_config, write_config, symbols, menus. |
| `Symbol`            | 4073–5597     | Config symbol (config FOO): type, value, visibility, defaults, select/imply. |
| `Choice`            | 5598–6218     | choice/endchoice block, selected symbol. |
| `MenuNode`          | 6219–6852     | Menu tree node (menu, if, config, etc.). |
| `Variable`          | 6853–6910     | Preprocessor-style variable (e.g. from Kconfig). |
| `KconfigError` etc. | 6911–6946     | Exceptions. |
| **Expression/helpers** | 6947–7870  | `expr_value`, `expr_str`, `_visibility`, `_depend_on`, `_shell_fn`, etc. |
| **Tree/action helpers** | 7871–end   | `_recursively_perform_action`, `_flatten`, `_remove_ifs`, etc. |

The file starts with a long **docstring** (lines ~44–140+) describing semantics: symbol values, visibility, defaults, select, and how `.config` is written.

### Other esp_kconfiglib modules

- **`constants.py`** — Enums and constants (e.g. `DefaultsPolicy`).
- **`report.py`** — `KconfigReport` and report areas (`DefaultValuesArea`, `MultipleDefinitionArea`, `MiscArea`, etc.).
- **`kconfig_grammar.py`** — Grammar/token layer (`KconfigGrammar`, `KconfigBlock`, parse errors).
- **`kconfig_parser.py`** — `Parser`, `Orphan` (parsing into the core model).

Public API: `esp_kconfiglib` exports `Kconfig` and `DefaultsPolicy` (see `__init__.py`).

## How to analyze

1. **Use semantic search** for behavior (e.g. “where is symbol visibility computed”, “how are choices finalized”).
2. **Cite by file and line range** (e.g. `esp_kconfiglib/core.py` lines 4073–4100) instead of pasting large blocks.
3. **Navigate by the map above** — jump to the class or helper range that matches the question.
4. **For repo-wide or multi-file exploration** (e.g. “all usages of MenuNode”, “full parsing pipeline”), consider using the **explore** subagent with a clear prompt and thoroughness level.

## Concepts worth knowing

- **Visibility** — A symbol is only assignable if its prompt condition is true; see docstring and `_visibility` / prompt conditions.
- **Symbol types** — bool, string, int, hex, float; type handling is in `Symbol` and related helpers.
- **Parsing flow** — `kconfig_parser` / `kconfig_grammar` produce structures consumed by `core.py` (e.g. `Kconfig` building the tree of `MenuNode` and `Symbol`/`Choice`).

## Docstring style

- Docstring content starts on a **new line** after the opening `"""`, and the closing `"""` is on its own line:
  ```python
  def foo():
      """
      This is the correct style.
      """
  ```
  Do **not** put text on the same line as the opening triple-quotes:
  ```python
  def foo():
      """This is wrong."""
  ```
- This applies to module, class, and function/method docstrings.
- Dataclass field docstrings (attribute docstrings) may remain inline.

## Type annotations

- This package is still backward compatible to at least Python 3.8 -> type annotatiotns needs to use dedicated types like List, Tuple
instead of list, tuple and Optional instead of "|".

## Type checks: `type()` vs `isinstance`

- **In code paths involved in parsing, `isinstance(...)` is forbidden.** Use
  `type(x) is SomeClass` (or `is not`) for type checks instead. `isinstance`
  walks the MRO and is materially slower than the identity check; this matters
  in the parser hot path. `type(x) is` is also recognised by mypy as a type
  narrowing pattern, so no `# type: ignore` is needed.
- In genuinely cold paths (e.g. one-time cleanup, error formatting, report
  rendering) `isinstance` is acceptable — but **ask before using it** in any
  new code so we keep a deliberate boundary.
- Note: `type(x) in (A, B)` is **not** recognised by mypy for narrowing.
  When checking against multiple types in a hot path, use chained
  `type(x) is A or type(x) is B`, or accept a `# type: ignore` if needed.

## Testing (kconfiglib / report)

- **`KconfigReport` is a singleton.** After any test that loads rename files, adds report records, or constructs `DeprecatedOptions`, call **`kconfig.report.reset()`** before the next test (or use a fresh `Kconfig` plus explicit reset) so Miscellaneous / other areas do not leak between cases.
- **Prefer checked-in fixtures over temporary files for test inputs.** Put rename files, `sdkconfig` snippets, and similar under e.g. `test/kconfiglib/deprecated/` (or the relevant component’s `test/` tree). Reserve `tempfile` for **outputs** (generated config/header) or ephemeral dirs (`sync_deps`) when committing the result is not desired.
- If the tests produce coverage files (`.coverage*`), delete them automatically
- **Follow existing test patterns.** Before writing new tests, look at nearby tests in the same file/class for conventions (setup, teardown, assertion style). Use pytest features — fixtures, `monkeypatch` (e.g. `monkeypatch.setenv`/`monkeypatch.delenv` for environment variables), `tmp_path`, parametrize — instead of manual `os.environ` manipulation, `try/finally` cleanup, or hand-rolled temp directories.


## Parsing

There are two parsers, both of them are supported:

- old one (basic logic in `esp_kconfiglib/core.py::parse_block()`)
- new one, based on `pyparsing`
    - grammar located in `esp_kconfiglib/kconfig_grammar.py`.
    - parser itself in `esp_kconfiglib/kconfig_parser.py`.

## Work with the repo, version control

* `dev_test_no_commit` folder is intended for testing, experiments etc. Do not revove anything there, but create new test/experiment files/scripts as needed
* `AGENTS.md` file is not to be committed or under version control. It is only a local file.

## Logging, log message style

`esp_pylib` is used for logging.

```python
import sys
from esp_pylib.logger import log
#...
log.set_info_stream(sys.stderr) # otherwise, lower level logs will end up in stdout
log.note(f"{file}:{line}: text of the message itself") # or debug, warn, err
log.print("User-facing message") # file, line mostly not needed
log.die("fatal error message")  # log + exit; prefer over bare sys.exit for CLI tools
```

If possible, log messages should follow the "file:line: msg" pattern if file and/or line are available.
The message itself should have non-capitalized first letter and should NOT be ended by any punctuation mark.
All the messages except user-facing are printed to `stderr`.
Use `log.set_info_stream(sys.stderr)` to set all the log levels to output to `stderr`.
When emitting Rich markup in log strings, escape untrusted/path text with `rich.markup.escape`.
Progress / status lines that must not mix with machine stdout (JSON, etc.) should use
`log.print(..., file=sys.stderr, markup=False)`.

## CLI: rich-click + esp_pylib

New or updated CLI entry points should follow **`kconfgen/core.py`** (also `kconfcheck`, `kconfserver`, `esp_menuconfig`):

* Argument parsing: `import rich_click as click` (not stdlib `argparse`).
* Decorate `main` with `@click.command(...)` / `@click.option` / `@click.argument`.
* Use `context_settings=dict(help_option_names=["-h", "--help"])`.
* Logging and fatal errors: `esp_pylib.logger.log` (`log.die`, `log.warn`, `log.print`, …).
* Call `install_exception_reporting()` from `esp_pylib.excepthook` in the CLI `main` (or `__main__`).
* Package deps already include `esp-pylib[cli]` (pulls in rich-click); do not add a separate argparse stack.

Example skeleton:

```python
import sys
import rich_click as click
from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log

@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("-t", "--target", required=True)
def main(target: str) -> None:
    install_exception_reporting()
    log.set_info_stream(sys.stderr)
    ...
```

In tests, invoke a click command with `main(argv, standalone_mode=False)` so it returns instead of raising `SystemExit`.

## Commit message style

Keep commit messages **short and focused**. Long explanations, rationale,
trade-offs, policy decisions, and per-file breakdowns belong in the **MR
description**, not in the commit body.

* **Subject:** conventional-commit form, imperative, ≤72 chars, e.g.
  `feat(test): add integration test skeleton and CI jobs`.
  Pick the right type: `feat`, `fix`, `change`, `remove`, `test`, `docs`,
  `refactor`, `ci`, `chore`.
* **Body:** at most one short paragraph (1–3 lines) stating *what* the
  commit does and *why*, in plain prose.
  * Do **not** enumerate touched files.
  * Do **not** list every flag/option/runner-tag/etc.
  * Do **not** explain manual vs automatic triggers, allow_failure,
    runner-capacity reasoning, etc. — that is MR-description material.
* **Footers:** do **not** add `Co-authored-by:` lines automatically.
  Only add a footer if the user explicitly asks for one.
* Prefer **few logical commits** over many small ones. When asked to
  refine history, fold follow-up changes into the existing logical
  commit they belong to (via `--amend` or interactive rebase) rather
  than stacking new "fixup-style" commits on top.

Example (matches the style used in this repo):

```
feat(menuconfig): enable headless mode in _main()

Allow the standalone menuconfig entry point to skip the interactive TUI
when MENUCONFIG_HEADLESS=1 is set, enabling CI and integration tests to
verify the CMake menuconfig target without a terminal.
```
