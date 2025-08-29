# Kconfig Tests

## kconfserver.py tests

Install pexpect (`pip install pexpect`).

Then run the tests manually:

```
cd <folder with kconfserver tests>
pytest
```

Note: ``kconfserver.py`` prints its error messages on stderr, to avoid overlap with JSON content on stdout. However pexpect uses a pty (virtual terminal) which can't distinguish stderr and stdout.

Test cases apply to `Kconfig` config schema. Cases are listed in `testcases.txt` and are each of this form:

```
* Set TEST_BOOL, showing child items
> { "TEST_BOOL" : true }
< { "values" : { "TEST_BOOL" : true, "TEST_CHILD_STR" : "OHAI!", "TEST_CHILD_BOOL" : true }, "ranges": {"TEST_CONDITIONAL_RANGES": [0, 100]}, "visible": {"TEST_CHILD_BOOL" : true, "TEST_CHILD_STR" : true} }

```

* First line (`*`) is description
* Second line (`>`) is changes to send. For version 3, there can be a (`>R`) leading string, which denotes that the following JSON snippet should be used with the `reset` command.
* Third line (`<`) is response to expect back
* (Blank line between cases)

Test cases are run in sequence, so any test case depends on the state changes caused by all items above it.
