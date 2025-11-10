Kconfserver
===========

``kconfserver.py`` is a small Python program intended to support IDEs and other clients that want to allow editing sdkconfig files, without needing to reproduce all of the kconfig logic in a particular program.

Currently, there are 3 protocol versions. See :ref:`kconfserver-protocol-changes` for details on the changes between versions. Examples in this document use version 3. For new projects, it is strongly recommended to use the latest protocol version.

After launching ``kconfserver.py``, the kconfserver communicates via JSON sent/received on stdout. Out-of-band errors are logged via stderr.

The basic idea of kconfserver is to provide a simple API for other applications to interact with the project configuration, so the user can change configuration options without the need of running CLI tools (such as ``menuconfig``). When the user opens configuration in IDE, it first requests all the config options from kconfserver and shows them in the UI. When the user changes some options, IDE sends the new values to kconfserver, which applies them to the configuration and notifies IDE about any changes in the configuration (e.g. other options became (in-)visible or changed value).

Detailed information about the interaction with kconfserver is provided in the following sections.

.. note::
    If you are using kconfserver with ESP-IDF framework, you can launch it via ``idf.py confserver`` command or ``confserver`` build target in ninja/make.

Configuration Structure
-----------------------

Before any meaningful interaction with the kconfserver, client must load a file containing the configuration structure (distant equivalent to a ``Kconfig`` file). This file contains information about all the menu items in the current configuration, together with their children (config options and sub-menus) and their relationships.

The format is currently undocumented. However, the format itself is supposed to be stable.

.. note::

    For examining of an existing configuration, ESP-IDF framework generates a file called ``kconfig_menus.json``. This file contains the structure of the configuration described above.

Initial Process
---------------

After initializing, the server will print ``Server running, waiting for requests on stdin...`` to stderr.

Then it will print a JSON dictionary on stdout, representing the initial state of the configuration (as described above):

.. code-block:: json

    {
    "version": 3,
    "ranges": {
                "TEST_CONFIG": [0, 10] },
    "visible": { "TEST_CONFIG": true,
                    "CHOICE_A": true,
                    "test-config-submenu": true },
    "values": { "TEST_CONFIG": 1,
                "CHOICE_A": true },
    "defaults": {"TEST_CONFIG": true,
                "CHOICE_A": true },
    "warnings": {"DANGEROUS_OPTION": "Warning message for DANGEROUS_OPTION"}
    }

* ``version`` key is the protocol version in use.
* ``ranges`` is a dictionary for any config symbol which has a valid integer range. The array value has two values for min/max.
* ``visible`` holds a dictionary showing initial visibility status of config symbols (identified by the config symbol name) and menus (which don't represent a symbol but are represented as an id "slug"). Both these names (symbol name and menu slug) correspond to the ``id`` key in ``kconfig_menus.json``.
* ``values`` holds a dictionary showing initial values of all config symbols. Invisible symbols are not included here.
* ``defaults`` holds a dictionary indicating if the config symbols have default value or not. This key is supported only in protocol version 3 and later. More information about default values can be found in the :ref:`defaults` section.
* ``warnings`` holds a dictionary with config symbol names as keys and their warning messages as values. If given (menu)config has no ``warning`` option, it is not included. For more information about a ``warning`` option, see :ref:`warning-option`. This key is supported only in protocol version 3 and later.

.. note::

    Actual output is not pretty-printed and will print on a single line. Order of dictionary keys is undefined.

Interaction
-----------

Interaction consists of the client sending JSON dictionary "requests" to the server one at a time. The server will respond to each request with a JSON dictionary response. Interaction is done when the client closes stdout (at this point the server will exit).

Requests look like:

.. code-block:: json

    {
    "version": 3,
    "set": { "TEST_CHILD_STR": "New value",
            "TEST_BOOL": true }
    }


.. note::

    Requests don't need to be pretty-printed, they just need to be in a valid JSON format.

The ``version`` key **must** be present in the request and must match a protocol version supported by the kconfserver.

The ``set`` key is optional. If present, its value must be a dictionary of new values to set on kconfig symbols.

Additional optional keys:

* ``load``: If this key is set, sdkconfig file will be reloaded from filesystem before any values are set applied. The value of this key can be a filename, in which case configuration will be loaded from this file. If the value of this key is ``null``, configuration will be loaded from the last used file. The response to a ``load`` command is always the full set of config values and ranges, the same as when the server is initially started.

* ``save``: If this key is set, sdkconfig file will be saved after any values are set. Similar to ``load``, the value of this key can be a filename to save to a particular file, or ``null`` to reuse the last used file.

* ``reset``: If this key is set, the server will reset the config symbols to their default values. The value of this key can be a list of config symbol names to reset, menu ID to recursively reset the menu and all of its submenus, or a list containing the special name ``all`` to reset all symbols at once. Menu ID can be found in the ``kconfig_menus.json`` file, under the ``id`` key of a specific menu item.

.. code-block:: json

    {
    "version": 3,
    "reset": ["TEST_CHILD_STR", "TEST_BOOL"]
    }

    {"version": 3, "reset": ["all"] }

After a request is processed, a response is printed to stdout similar to this:

.. code-block:: json

    {
    "version": 2,
    "ranges": {},
    "visible": { "test-config-submenu": false},
    "values": { "SUBMENU_TRIGGER": false }
    "defaults": { "SUBMENU_TRIGGER": false }
    }

* ``version`` is the protocol version used by the server.
* ``ranges`` contains any changed ranges, where the new range of the config symbol has changed (due to some other configuration change or because a new sdkconfig has been loaded).
* ``visible`` contains any visibility changes, where the visible config symbols have changed.
* ``values`` contains any value changes, where a config symbol value has changed. This may be due to an explicit change (ie the client ``set`` this value), or a change caused by some other change in the config system. Note that a change which is set by the client may not be reflected exactly the same in the response, due to restrictions on allowed values which are enforced by the config server. Invalid changes are ignored by the config server.
* ``defaults`` contains any changes to the default values of config symbols. The key is always present in the response, but may be empty if no defaults have changed. This is only present in protocol version 3 and later.

If setting a value also changes the possible range of values that an item can have, this is also represented with a dictionary ``ranges`` that contains key/value pairs of config items to their new ranges:

.. code-block:: json

    {
    "version": 3,
    "values": {"OTHER_NAME": true },
    "visible": { },
    "ranges" : { "HAS_RANGE" : [ 3, 4 ] }
    "defaults": { "HAS_RANGE": false }
    }


.. note::

    The configuration server does not automatically load any changes which are applied externally to the ``sdkconfig`` file. Send a ``load`` command or restart the server if the file is externally edited.

.. note::

    The configuration server does not re-run CMake to regenerate other build files or metadata files after ``sdkconfig`` is updated. This will happen automatically the next time ``CMake`` or ``idf.py`` is run.

Kconfig Symbol Types
--------------------

* ``string`` types are represented as JSON strings.
* ``bool`` type is represented as JSON Boolean.
* ``int`` types are represented as JSON integers.
* ``hex`` types are also represented as JSON integers, clients should read the separate metadata file to know if the UI representation is ``int`` or ``hex``. It is possible to set a ``hex`` item by sending the server a JSON string of hex digits (no prefix) as the value, but the server always sends ``hex`` values as JSON integers.

Error Responses
---------------

In some cases, a request may lead to an error message. In this case, the error message is printed to stderr but an array of errors is also returned in the ``error`` key of the response:

.. code-block:: json

    {
      "version": 777,
      "error": [ "Unsupported request version 777. Server supports versions 1-3" ]
    }


These error messages are intended to be human readable, not machine parsable.

.. _kconfserver-protocol-changes:

Protocol Version Changes
------------------------

* V3: Added the ``defaults`` key to the response. This holds a dictionary showing the information if given config symbol has a default value or not.
* V3: Added the ``reset`` key allowing to set a config symbol to its default value.
* V2: Added the ``visible`` key to the response. Invisible items are no longer represented as having value null.
* V2: ``load`` now sends changes compared to values before the load, not the whole list of config items.
