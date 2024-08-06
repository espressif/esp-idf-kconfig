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
