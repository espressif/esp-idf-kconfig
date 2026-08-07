.. _kcompare:

Comparing Kconfig Between Commits
=================================

The ``kcompare`` tool reports how the Kconfig configuration options of ESP-IDF change between two commits (or tags/branches). It lists configuration options and choices that were **added**, **removed**, or **renamed**, and config options/choices whose **default values** changed.

Overview
--------

``kcompare`` answers questions such as:

- Which config options and choices appeared or disappeared between ``v6.0`` and ``v6.1``?
- Which options were renamed (and is the ``sdkconfig.rename`` record present)?
- Which options changed their default value, and how?
- Did a change reach all targets, or only some of them?

The comparison is always **older → newer**, so the direction of *added* / *removed* stays meaningful. ``kcompare`` decides which commit is older by trying, in order:

1. **Git ancestry** — if one commit is an ancestor of the other, it is the older one.
2. **ESP-IDF version** — if the commits have diverged (neither is an ancestor of the other), the ``ESP_IDF_VERSION_MAJOR``/``MINOR``/``PATCH`` macros from ``esp_idf_version.h`` decide it. This covers release/backport branches, for example ``release/v6.0``, which can carry commits made *after* ``v6.1-beta1`` was tagged without being functionally newer.
3. **Argument order** — if neither of the above can decide, ``kcompare`` assumes ``commit1`` is older and ``commit2`` is newer, and prints a warning so the choice is not silent.

How It Works
------------

For each of the two commits, ``kcompare``:

1. Creates a temporary git worktree for the commit under ``.kcompare/worktrees/``.
2. Sets up the ESP-IDF environment for that worktree using `eim <https://docs.espressif.com/projects/idf-im-ui/en/latest/>`_ (the ESP-IDF Installation Manager) and captures the environment needed to run the configuration engine.
3. Collects the root ``Kconfig``, all ``sdkconfig.rename`` files, and the component source-file lists, mimicking how ESP-IDF prepares inputs for ``kconfgen``. This corresponds to a virtual project that includes all components.
4. Runs the configuration engine (``kconfgen``) and creates a *configuration snapshot* — only the data needed for the comparison (option and choice names, default values, rename records).

The two snapshots are then compared and the result is rendered in the requested format.

.. note::

    ``eim`` must be installed and on ``PATH``. If it is missing, ``kcompare`` stops with a hint on how to install it.

Prerequisites and Installation
------------------------------

- ``kcompare`` must be invoked from an ESP-IDF repository root (the directory containing the top-level ``Kconfig`` file).
- The ``esp-idf-kconfig`` package must be installed (it ships with ESP-IDF, or can be installed standalone with ``pip install esp-idf-kconfig``).
- `eim <https://docs.espressif.com/projects/idf-im-ui/en/latest/>`_ must be available for environment setup (see the note above).

Usage
-----

.. code-block:: console

    python -m kcompare <commit1> <commit2> [output_file] [options]

Positional arguments:

- ``commit1``, ``commit2`` — the two commits or tags to compare. Their order usually does not matter; ``kcompare`` determines which one is older via git ancestry, then ESP-IDF version numbers, and only falls back to treating ``commit1`` as older when neither can decide (see Overview above).
- ``output_file`` *(optional)* — destination path for the report. When omitted (or set to ``-``), the report is written to standard output.

Options:

- ``-t, --target <chip>`` — the chip target to build the configuration for (for example ``esp32``, ``esp32s3``). When omitted, ``kcompare`` compares every target common to both commits (discovered via ``idf.py --list-targets``) and combines the results.
- ``-o, --output <format>`` — output format: ``human`` (default, colorized console), ``markdown``, or ``json``.
- ``--aggregation <mode>`` — how to group the changes: ``change`` (default), ``target``, or ``aggregated``. See :ref:`kcompare-aggregation` for details.
- ``--by-codeowner`` — split the report by codeowner group, using ``.gitlab/CODEOWNERS`` from the newer commit from ESP-IDF repository. See :ref:`kcompare-codeowner` for details.
- ``--skip-install`` — skip the ``eim install`` step (still captures the environment via ``eim run``); useful when the ESP-IDF toolchains and Python dependencies are already set up.
- ``--keep-worktrees`` — do not delete the temporary git worktrees under ``.kcompare/worktrees/`` (for later inspection or re-runs).
- ``-v, --verbose`` — show raw ``eim`` / ``idf.py`` output and Kconfig parser notes, which are suppressed by default.

.. note::

    Progress and diagnostic messages are written to ``stderr``. The report itself is written to the output file or to ``stdout``, so capturing ``stdout`` always yields a clean report (see :ref:`kcompare-ci`).

Example usage — compare two commits for a single target and print a Markdown report:

.. code-block:: console

    python -m kcompare v6.0 v6.1 -t esp32 -o markdown

Example usage — compare across all common targets and write JSON to a file:

.. code-block:: console

    python -m kcompare v6.0 v6.1 report.json -o json

What Gets Compared
------------------

``kcompare`` reports the following categories:

- **Added** — config options (and choices) present in the newer commit but not in the older one.
- **Removed** — config options (and choices) present in the older commit but not in the newer one.
- **Renamed** — a config option ``A_OLD`` in the older commit and ``A_NEW`` in the newer commit, **where a matching record exists in an** ``sdkconfig.rename`` file in the newer commit.
- **Defaults changed** — config options (and choices) whose list of ``default`` definitions differs.

Renames are only reported when a ``sdkconfig.rename`` record is present in the newer commit. The concept of "renaming" is otherwise ambiguous — prompt, defaults, or location may also change — so without a rename record ``kcompare`` cannot tell a rename from an unrelated remove + add. A missing rename record therefore shows up as the old name under **Removed** and the new name under **Added**, which is a useful signal that the record is missing.

Default values are compared lexically: ``kcompare`` compares the ordered list of ``default`` definitions as strings, including any ``if`` condition. As a consequence, a change to only the *order* of defaults, or a condition that references a renamed symbol (``default !A_OLD`` vs. ``default !A_NEW``), is reported as a change in default values.

.. _kcompare-aggregation:

Aggregation Modes
-----------------

When comparing more than one target, the same change often appears for several targets. The ``--aggregation`` option controls how the results are grouped. All three modes contain the same information; they differ only in how it is organized.

``change`` (default)
    One flat report where each individual change carries a ``targets_affected`` field listing the targets it applies to. This is the most convenient view for "what changed, and where?" questions.

``target``
    De-facto standalone diffs, one section per target. This is the single-target report repeated for each target. Useful when debugging a specific chip (for example, "something stopped working between ``v6.0`` and ``v6.1`` on ``esp32p4``; what changed there?"). Less convenient when you care about the change itself rather than a specific chip.

``aggregated``
    The same structure as ``target``, but each entry is keyed by a set of targets instead of a single target. Identical changes are merged, removing duplication. The group whose target set equals every compared target is the "all" group; its contents are the changes that were propagated to every chip. Inspecting the "all" group together with the per-subset groups answers questions like "was this change propagated to *all and only* the intended targets?".

.. _kcompare-json:

JSON Output and Schema
----------------------

Use ``-o json`` for machine-readable output. Every JSON document has a stable **preamble** followed by a ``reports`` field whose shape depends on the aggregation mode.

Preamble (present in all modes)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- ``aggregation`` *(str)* — ``"change"``, ``"target"``, or ``"aggregated"``.
- ``older_commit`` / ``newer_commit`` *(str)* — the commit refs as given on the command line.
- ``older_sha`` / ``newer_sha`` *(str)* — the resolved full commit SHAs.
- ``targets_compared`` *(list of str)* — targets actually compared (present in both commits).
- ``targets_skipped`` *(list of object)* — targets present in only one commit and therefore not compared. Each item has ``target``, ``present_in`` (the commit ref where it exists), and ``missing_from`` (the commit ref where it is absent).

.. important::

    The ``reports`` field is an **object** in ``change`` mode (the default), but a **list** in ``target`` and ``aggregated`` modes. Branch on ``aggregation`` (or on the requested mode) before parsing ``reports``.

The change body
^^^^^^^^^^^^^^^

All modes reuse the same set of category buckets:

- ``added`` / ``removed`` — options by name.
- ``renamed`` — objects with ``old_name``, ``new_name``, and ``inverted`` (``true`` when the rename also inverts the value).
- ``defaults_changed`` — objects with ``id`` (symbol name, or choice id — a name or a ``file:line`` location for unnamed choices), ``kind`` (``"symbol"`` or ``"choice"``), the ordered ``old_defaults`` / ``new_defaults`` string lists, ``old_default_symbols`` / ``new_default_symbols`` (the default target symbol names, for choices), and ``old_options`` / ``new_options`` (the choice's member option names; empty for symbols).
- ``choices_added`` / ``choices_removed`` — objects with ``id`` and ``options`` (the choice's member config names).

How each mode presents these buckets:

- ``change`` — ``reports`` is a single body object; every item is an object annotated with a ``targets_affected`` list. Because the annotation lives on the item, ``added``/``removed`` are lists of objects (for example ``{"name": "FOO", "targets_affected": ["esp32"]}``) rather than plain strings.
- ``target`` — ``reports`` is a list; each entry is one target's body plus a ``target`` field. ``added``/``removed`` are plain string lists.
- ``aggregated`` — ``reports`` is a list; each entry is a body plus a ``targets`` list. The entry covering every compared target is the "all" group; when 2+ targets were compared its ``targets`` is folded to the ``["all"]`` sentinel. ``added``/``removed`` are plain string lists.

.. note::

  When running ``kcompare`` for at least two targets and given change affects all targets, instead of verbosely listing all targets, the ``targets_affected`` field is folded to the single value ``["all"]`` for readability. In the Markdown output the same situation is rendered as *all chips*.

Example — ``change`` mode (default)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: json

    {
      "aggregation": "change",
      "older_commit": "v6.0",
      "older_sha": "aaaaaaaaaaaa...",
      "newer_commit": "v6.1",
      "newer_sha": "bbbbbbbbbbbb...",
      "targets_compared": ["esp32", "esp32s2"],
      "targets_skipped": [
        {"target": "esp32c3", "present_in": "v6.1", "missing_from": "v6.0"}
      ],
      "reports": {
        "added": [
          {"name": "COMMON", "targets_affected": ["all"]},
          {"name": "ESP32_ONLY", "targets_affected": ["esp32"]}
        ],
        "removed": [],
        "renamed": [
          {"old_name": "A_OLD", "new_name": "A_NEW", "inverted": false,
           "targets_affected": ["all"]}
        ],
        "defaults_changed": [
          {"id": "FOO", "kind": "symbol",
           "old_defaults": ["y"], "new_defaults": ["n"],
           "old_default_symbols": [], "new_default_symbols": [],
           "old_options": [], "new_options": [],
           "targets_affected": ["all"]}
        ],
        "choices_added": [
          {"id": "MYCHOICE", "options": ["CHOICE_A", "CHOICE_B"],
           "targets_affected": ["esp32"]}
        ],
        "choices_removed": []
      }
    }

Example — ``target`` mode
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: json

    {
      "aggregation": "target",
      "older_commit": "v6.0",
      "older_sha": "aaaaaaaaaaaa...",
      "newer_commit": "v6.1",
      "newer_sha": "bbbbbbbbbbbb...",
      "targets_compared": ["esp32", "esp32s2"],
      "targets_skipped": [
        {"target": "esp32c3", "present_in": "v6.1", "missing_from": "v6.0"}
      ],
      "reports": [
        {
          "target": "esp32",
          "added": ["COMMON", "ESP32_ONLY"],
          "removed": [],
          "renamed": [{"old_name": "A_OLD", "new_name": "A_NEW", "inverted": false}],
          "defaults_changed": [
            {"id": "FOO", "kind": "symbol",
             "old_defaults": ["y"], "new_defaults": ["n"],
             "old_default_symbols": [], "new_default_symbols": [],
             "old_options": [], "new_options": []}
          ],
          "choices_added": [
            {"id": "MYCHOICE", "options": ["CHOICE_A", "CHOICE_B"]}
          ],
          "choices_removed": []
        },
        {
          "target": "esp32s2",
          "added": ["COMMON"],
          "removed": [],
          "renamed": [{"old_name": "A_OLD", "new_name": "A_NEW", "inverted": false}],
          "defaults_changed": [
            {"id": "FOO", "kind": "symbol",
             "old_defaults": ["y"], "new_defaults": ["n"],
             "old_default_symbols": [], "new_default_symbols": [],
             "old_options": [], "new_options": []}
          ],
          "choices_added": [],
          "choices_removed": []
        }
      ]
    }

Example — ``aggregated`` mode
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: json

    {
      "aggregation": "aggregated",
      "older_commit": "v6.0",
      "older_sha": "aaaaaaaaaaaa...",
      "newer_commit": "v6.1",
      "newer_sha": "bbbbbbbbbbbb...",
      "targets_compared": ["esp32", "esp32s2"],
      "targets_skipped": [
        {"target": "esp32c3", "present_in": "v6.1", "missing_from": "v6.0"}
      ],
      "reports": [
        {
          "targets": ["all"],
          "added": ["COMMON"],
          "removed": [],
          "renamed": [{"old_name": "A_OLD", "new_name": "A_NEW", "inverted": false}],
          "defaults_changed": [
            {"id": "FOO", "kind": "symbol",
             "old_defaults": ["y"], "new_defaults": ["n"],
             "old_default_symbols": [], "new_default_symbols": [],
             "old_options": [], "new_options": []}
          ],
          "choices_added": [],
          "choices_removed": []
        },
        {
          "targets": ["esp32"],
          "added": ["ESP32_ONLY"],
          "removed": [],
          "renamed": [],
          "defaults_changed": [],
          "choices_added": [
            {"id": "MYCHOICE", "options": ["CHOICE_A", "CHOICE_B"]}
          ],
          "choices_removed": []
        }
      ]
    }

.. _kcompare-codeowner:

Splitting the Report by Codeowner
---------------------------------

With ``--by-codeowner``, ``kcompare`` splits a single comparison into one report per codeowner group, so each team sees only the changes in the components it owns. This is convenient for routing release-note or regression review to the right people.

Ownership is resolved from the ``.gitlab/CODEOWNERS`` file of the **newer** commit. Only the ``/components`` rules are used: the path after ``/components`` identifies the component (a directory, possibly with a ``*`` wildcard) and the groups are the names after ``@esp-idf-codeowners/`` (nested names such as ``app-utilities/console`` are kept). When several rules match a path, the **last** matching rule wins, mirroring GitLab's own behavior.

Older tags (for example ``v6.0`` and ``v6.1-beta1``) often ship a CODEOWNERS file trimmed for easier backports: a catch-all ``*`` rule and fewer than ten ``/components`` entries.
In that case ``kcompare`` warns and walks the last three commits that modified ``.gitlab/CODEOWNERS`` on the newer side, using the newest revision that still has at least ten ``/components`` rules (typically the pre-trim parent).
If none qualifies, it falls back to ``master:.gitlab/CODEOWNERS`` from the repository being compared.

Each changed option or choice is attributed to a group based on where it is *defined* (the ``Kconfig`` file path of its definition):

- A change defined in a component maps to that component's groups.
- A symbol or choice defined in **several** components (multiple definitions) is attributed to the union of all those components' groups.
- A change whose definition path does **not** match any ``/components`` rule (for example a symbol defined in the root ``Kconfig``) is attributed to **every** group, so that no owner misses it.

Only groups that end up with at least one change are emitted.

``--by-codeowner`` combines with ``--aggregation``: the report is first built in the requested aggregation mode and then split, so each group's report keeps the same shape (``change``, ``target``, or ``aggregated``).

Output depends on whether an ``output_file`` is given:

- **No output file (stdout).** For ``human`` and ``markdown``, the group reports are printed one after another, each preceded by a ``Report for codeowner group <name>`` header. For ``json``, a single object is emitted with the usual preamble plus a ``codeowner_groups`` field mapping each group name to its report, so the output stays valid JSON.
- **With an output file.** The path is treated as a template: ``report.json`` becomes ``report_<group>.json`` (for example ``report_system.json``), with ``/`` in nested group names replaced by ``_`` (``app-utilities/console`` becomes ``app-utilities_console``). Each file is a normal single-group report and its preamble carries a ``codeowner_group`` field.

.. note::

    ``--by-codeowner`` requires a usable CODEOWNERS source: the newer checkout's file (at least ten ``/components`` rules), else a recent pre-trim revision of that file, else ``master:.gitlab/CODEOWNERS``.
    If the newer file is missing, or none of those sources clears the threshold, ``kcompare`` stops with an error.
    The ``master`` ref must be available in the local repository for the last-resort fallback to work.

Example — split a Markdown report to standard output:

.. code-block:: console

    python -m kcompare v6.0 v6.1 -o markdown --by-codeowner

Example — split JSON into one file per group:

.. code-block:: console

    python -m kcompare v6.0 v6.1 report.json -o json --by-codeowner

.. _kcompare-ci:

Using kcompare in CI
--------------------

``kcompare`` is designed to run unattended in CI. Recommendations:

- **Capture standard output as JSON.** Run with ``-o json`` and either write to an ``output_file`` or read standard output. Progress and log messages go to standard error, so standard output is always a clean JSON document.
- **Pick the aggregation for your check.** ``change`` is the default and is usually the most convenient for automated rules ("fail if any option was removed", "warn on default changes"), because each change lists the targets it affects. Use ``aggregated`` to assert propagation across targets, or ``target`` for a per-chip report.
- **Watch** ``targets_skipped``. A non-empty list means a target exists on only one side of the comparison; depending on your policy this may warrant a warning.
- **Set up the environment once.** If your job already has the ESP-IDF checkout prepared with ``eim``, pass ``--skip-install`` to save time.

Minimal example that fails the job when any option is removed on any target:

.. code-block:: console

    python -m kcompare "$BASE" "$HEAD" report.json -o json --aggregation change

.. code-block:: python

    import json, sys

    data = json.load(open("report.json"))

    removed = data["reports"]["removed"]  # 'change' mode: reports is an object
    if removed:
        for item in removed:
            print(f"removed: {item['name']} on {', '.join(item['targets_affected'])}", file=sys.stderr)
        sys.exit(1)
