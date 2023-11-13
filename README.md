# esp-idf-kconfig

The ```esp-idf-kconfig``` package is part of the [ESP-IDF](https://github.com/espressif/esp-idf) SDK for Espressif products and is automatically installed.

It is responsible for enabling project configuration using the ```kconfig``` language, providing IDE support for configuration and configuration documentation generation.

For more information about how it works go to the [documentation](https://github.com/espressif/esp-idf-kconfig/blob/master/docs/DOCUMENTATION.md).

## Contributing

### Code Style & Static Analysis

Please follow these coding standards when writing code for ``esp-idf-kconfig``:

#### Pre-commit checks

[pre-commit](https://pre-commit.com/) is a framework for managing pre-commit hooks. These hooks help to identify simple issues before committing code for review.

To use the tool, first install ``pre-commit``. Then enable the ``pre-commit`` and ``commit-msg`` git hooks:

```sh
python -m pip install pre-commit
pre-commit install -t pre-commit -t commit-msg
```

On the first commit ``pre-commit`` will install the hooks, subsequent checks will be significantly faster. If an error is found an appropriate error message will be displayed.


#### Conventional Commits

``esp-idf-kconfig`` complies with the [Conventional Commits standard](https://www.conventionalcommits.org/en/v1.0.0/#specification). Every commit message is checked with [Conventional Precommit Linter](https://github.com/espressif/conventional-precommit-linter), ensuring it adheres to the standard.
