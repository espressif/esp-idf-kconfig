Contributions Guide
===================

We welcome contributions - fixing bugs, adding features, adding documentation, etc. - to the ``esp-idf-kconfig`` package on GitHub. This guide provides information on how to contribute to the project.

How to Contribute
-----------------

1. Fork the repository on GitHub and setup your local development package:

::

        $ git clone git@github.com:espressif/esp-idf-kconfig.git
        $ cd esp-idf-kconfig
        $ pip install -e ".[dev]"

By setting up the package in editable mode, you can make changes to the code and test them without having to reinstall the package.

2. Install `pre-commit <https://pre-commit.com/>`_. which is a framework for managing pre-commit hooks. These hooks help to identify simple issues before committing code for review. You can install it by running:

::

        $ pip install pre-commit
        $ pre-commit install -t pre-commit -t commit-msg


This will install the pre-commit hooks to your repository. You can run the checks manually by running: ``pre-commit run``, but pre-commit will run automatically before every commit. On the first commit ``pre-commit`` will install the hooks, subsequent checks will be significantly faster. If an error is found an appropriate error message will be displayed.

3. Create new branch for your changes. We are using `conventional commits <https://www.conventionalcommits.org/en/v1.0.0/>`_ for commit messages and try to reflect this for branch names as well. For example, if you are fixing a bug, you can name your branch ``fix/<short_description>``, e.g. ``fix/support_long_config_names``.

::

            $ git checkout -b <branch-name>

4. Before making your changes, please refer to :ref:`code style <kconfcheck>` to make sure your changes will be compliant with our code style. Then, make your changes and test them. We are using `pytest <https://docs.pytest.org/en/latest/>`_ for testing. It is a good practice to write tests for your changes. Details about testing the ``esp-idf-kconfig`` package can be found in the :ref:`Writing tests <writing-tests>` section.

5. Commit your changes. ``esp-idf-kconfig`` complies with the `Conventional Commits standard <https://www.conventionalcommits.org/en/v1.0.0/#specification>`_. Every commit message is checked with `Conventional Precommit Linter <https://github.com/espressif/conventional-precommit-linter>`_, ensuring it adheres to the standard.

6. Push your changes to your fork and create a pull request. We are using `GH Pull Requests <https://github.com/espressif/esp-idf-kconfig/pulls>`_ for code review. Please make sure that your PR passes the CI checks.

7. Wait for the review. We will review your changes and provide feedback. If everything is OK, we will merge your PR. Alternatively, we may ask you to make some changes.
