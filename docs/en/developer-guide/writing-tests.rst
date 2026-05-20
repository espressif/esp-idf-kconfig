Writing Tests for ``esp-idf-kconfig``
=====================================

.. _writing-tests:

Tests are written using the `pytest <https://docs.pytest.org/en/latest/>`_ and `unittest <https://docs.python.org/3/library/unittest.html>`_ frameworks, where ``pytest`` is preferred for the new tests. The tests are located in the ``tests/<subpackage>`` directory of the repository.

All the tests can be run locally from the root of the repository by running:

::

    $ pytest


Testing ``kconfiglib``
----------------------

Tests for ``kcofiglib`` are pytest-based. Testing kconfiglib is widely based on directly creating ``Kconfig`` object with given file and checking the output (and error output, if necessary). Thanks to ``pytest``, there is no need to create test case for every kconfig file you want to test, it is enough to add new ``<TestCase.in>``, ``<TestCase.out>`` and possibly ``<TestCase.err>``, where ``<TestCase>`` should describe what is tested. There are three subfolders in the ``tests/kconfiglib`` directory: ``ok``, ``warnings`` and ``errors`` corresponding to the expected behaviors of the tests.

- ``<TestCase.in>`` is a kconfig file that will be used as input for the test.
- ``<TestCase.out>`` is a file that contains expected output of the test. The content of the file is directly compared to the actual output of kconfiglib.
- ``<TestCase.err>`` is a file that contains expected error output of the test. Because error messages may vary in some details (e.g. paths can be different) or the order of the messages may change, the error output is compared to the actual output of kconfiglib in a more relaxed way. The error output is considered correct if all lines in the ``<TestCase.err>`` file are present in the actual output of kconfiglib. However, the actual output may contain more data than the ``<TestCase.err>`` file.


Testing ``menuconfig``
----------------------

``menuconfig`` is built on top of `Textual <https://textual.textualize.io/>`_, and it should be primarily tested using Textual's built-in test harness — the `Pilot <https://textual.textualize.io/guide/testing/>`_ API (``App.run_test()``). Pilot drives the running app in-process, lets the tests simulate key presses and mouse events, inspect the live widget tree, and assert on rendered state. This is the preferred way to test menuconfig behavior: navigation, key bindings, widget state, prompt visibility, saving the configuration, and so on. Whenever a test can reasonably be expressed with Pilot, developers should use Pilot rather than ad-hoc alternatives.

The standalone menuconfig entry point (``python -m esp_menuconfig``) also supports the ``MENUCONFIG_HEADLESS=1`` environment variable, which skips the interactive TUI and immediately returns after loading the configuration. This mode is intentionally limited and exists only for cases where Pilot is not suitable — most notably for verifying that the CMake ``menuconfig`` target wires everything up correctly in integration/CI environments without launching a full TUI session. It should not be used as a substitute for proper Pilot-based tests of menuconfig behavior.
