#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# gen_kconfig_doc - kconfgen.py support for generating ReST markup documentation
#
# For each option in the loaded Kconfig (e.g. 'FOO'), CONFIG_FOO link target is
# generated, allowing options to be referenced in other documents
# (using :ref:`CONFIG_FOO`)
#
# SPDX-FileCopyrightText: 2017-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import re

import esp_kconfiglib.core as kconfiglib

# Indentation to be used in the generated file
INDENT = "    "

# Characters used when underlining section heading
HEADING_SYMBOLS = '#*=-^"+'

# Keep the heading level in sync with api-reference/kconfig.rst
INITIAL_HEADING_LEVEL = 3
MAX_HEADING_LEVEL = len(HEADING_SYMBOLS) - 1
EXCLUDED_MENU_NAMES = [
    "Configuration for components not included in the build",
    "Project configuration for components not included in the build",
]

# Comparison operators whose truth value is fixed once all operands are target-constant.
_COMPARISON_OPS = frozenset(
    [
        kconfiglib.EQUAL,
        kconfiglib.UNEQUAL,
        kconfiglib.LESS,
        kconfiglib.LESS_EQUAL,
        kconfiglib.GREATER,
        kconfiglib.GREATER_EQUAL,
    ]
)


class ConfigTargetVisibility(object):
    """
    Determine the visibility of Kconfig options based on IDF targets. Note that other environment variables should not
    imply invisibility and neither dependencies on visible options with default disabled state. This difference makes
    it necessary to implement our own visibility and cannot use the visibility defined inside Kconfiglib.

    An option is hidden only when it can never become visible for the current IDF_TARGET, i.e. its dependency
    reduces to n once every symbol the user cannot change for this target is folded to its constant value. See
    _is_item_target_constant for what "user cannot change" means (promptless symbols, prompts gated off by the target,
    symbols force-selected by a target-constant source, unsatisfiable dependencies).
    """

    def __init__(self, kconfig, target):
        # target actually is not necessary here because kconfiglib.expr_value() will evaluate it internally
        self.kconfig = kconfig
        self.visibility = dict()  # node name to (x, y) mapping where x is the visibility (True/False) and y is the
        # name of the config which implies the visibility
        self.target_env_var = "IDF_TARGET"
        self._constants_cache = dict()  # symbol name -> bool, memoizes _is_item_target_constant across the recursion

    def _is_item_target_constant(self, item):
        """
        True if the user cannot change item's value for the current IDF_TARGET (even indirectly).

        Algorithm: Start from the queried item and recurse down into what determines its value (rev_dep and
        defaults), in a tree-like structure. The recursion bottoms out at IDF_TARGET/IDF_TARGET_* (the only truly
        fixed inputs) and other (possibly already evaluated) target-constants, which are the recursion stoppers.

        A symbol counts as target-constant when its value and state is fully dependent (even
        transitively) on symbols with already constant value/state from the target alone:
            * a symbol force-selected on by a target-constant source is pinned to y;
            * a permanently disabled symbol (dependency evaluated as constant n - either on
              IDF_TARGET or on a target-constant source) is pinned to n;
            * invisible symbols (without prompt or prompt target-constantly disabled) with an
              unconditional default, or a conditional default whose condition folds to y, are
              pinned to their default value;
            * undefined symbols (referenced but never defined for this target, e.g. an omitted
              SOC_* cap) are pinned to n;

        Note: symbols whose value is derived from an environment variable are treated
        differently when the envvar was set at config generation time:
            1) envvar unset: config treated as free even though it would otherwise be
               target-constant;
            2) envvar set: configuration system treats the envvar reference as a string
               literal and the symbol may be target-constant.
        Envvars are expanded at parse time; after expansion there is no record that a string
        value came from an envvar.
        """
        if type(item) is not kconfiglib.Symbol:
            return False
        if item.name.startswith(self.target_env_var):
            # IDF_TARGET / IDF_TARGET_* symbols are target-constant
            return True
        if item.is_constant:
            # y/n or literals
            return True
        if self._depends_on_env_var(item):
            # Value comes from an environment variable, which is not fixed by the target: another build
            # could set it differently, so keep it free and let its dependents stay documented. (A variable set at
            # build time is folded away at parse time and never reaches here, so it is treated as constant.)
            return False
        if item.orig_type == kconfiglib.UNKNOWN:
            # A node-less UNKNOWN symbol is undefined: referenced but never defined for this target (e.g. an omitted
            # SOC_* cap, or a bogus `depends on <choice_name>` -- a choice name is not a value and kconfiglib itself
            # reports it as undefined). It is a hard n on every target -- no prompt, no default, and a type-less symbol
            # cannot be promoted by select/imply -- so treat it as target-constant and let its dependents be hidden.
            return not item.nodes

        sym_is_const = self._constants_cache.get(item.name)
        if sym_is_const is not None:
            return sym_is_const

        if _minimize_expr(item.rev_dep, self, self.kconfig) is self.kconfig.y:
            # Force-selected on by a strong reverse dependency that holds for this target (e.g. IDF_TARGET_X select
            # FOO).
            is_constant = True
        elif any(node.prompt is not None and self._visible(node)[0] for node in item.nodes):
            # The user can set it directly through a reachable prompt (and symbol is not force-selected).
            is_constant = False
        else:
            # Promptless or target-gated: constant iff everything determining its value is target-constant.
            is_constant = self._expr_is_target_constant(item.rev_dep) and all(
                self._expr_is_target_constant(cond) and self._expr_is_target_constant(value)
                for value, cond in item.defaults
            )

        self._constants_cache[item.name] = is_constant
        return is_constant

    def _depends_on_env_var(self, item):
        """
        True if item's value derives from a non-IDF_TARGET environment variable, via either 'option env="NAME"' or an
        unresolved '${NAME}' left in a default because NAME was unset at parse time. Macros ('$(NAME)') and env vars
        that were set at build time are expanded away during parsing, so they never look env-driven here.
        """
        env = item.env_var  # set only by 'option env="NAME"'
        if env and not env.startswith(self.target_env_var):
            return True
        return any(
            _references_unresolved_env(value, self.target_env_var)
            or _references_unresolved_env(cond, self.target_env_var)
            for value, cond in item.defaults
        )

    def _expr_is_target_constant(self, expr):
        """
        True if every symbol referenced in expr is target-constant, i.e. the whole expression evaluates to a value
        fixed by the current IDF_TARGET.
        """
        if type(expr) is tuple:
            return all(self._expr_is_target_constant(sub) for sub in expr[1:])
        return self._is_item_target_constant(expr)

    def _implies_invisibility(self, item):
        # Invisible iff the dependency reduces to n once target-constant symbols are folded to their values.
        return (_minimize_expr(item, self, self.kconfig) is self.kconfig.n, None)

    def _visible(self, node):
        if node.item == kconfiglib.COMMENT:
            return (False, None)
        if type(node.item) is kconfiglib.Symbol or type(node.item) is kconfiglib.Choice:
            dependencies = node.item.direct_dep  # "depends on" for configs
            name_id = node.item.name
            simple_def = len(node.item.nodes) <= 1  # defined only in one source file
            # Probably it is not necessary to check the default statements.
        else:
            # A menu is hidden when either its "visible if" or its own "depends on" (node.dep) is a hard n for this
            # target. node.dep carries the menu's "depends on" plus deps inherited from enclosing if/menu blocks; it is
            # not part of node.visibility, so fold both. Without node.dep, a menu gated off by an (undefined/omitted)
            # dependency would still emit an empty heading even though all its children are hidden.
            dependencies = self.kconfig._make_and(node.visibility, node.dep)
            name_id = node.prompt[0]
            simple_def = False  # menus can be defined with the same name at multiple locations and they don't know
            # about each other like configs through node.item.nodes. Therefore, they cannot be stored and have to be
            # re-evaluated always.

        try:
            (visib, source) = self.visibility[name_id]
        except KeyError:

            def invert_first_arg(_tuple):
                return (not _tuple[0], _tuple[1])

            (visib, source) = self._visible(node.parent) if node.parent else (True, None)

            if visib:
                (visib, source) = invert_first_arg(self._implies_invisibility(dependencies))

            if simple_def:
                # Configs defined at multiple places are not stored because they could have different visibility based
                # on different targets. kconfiglib.expr_value() will handle the visibility.
                self.visibility[name_id] = (visib, source)

        return (
            visib,
            source,
        )  # not used in "finally" block because failure messages from _implies_invisibility are
        # this way more understandable

    def visible(self, node):
        if not node.prompt:
            # don't store this in self.visibility because don't want to stop at invisible nodes when recursively
            # searching for invisible targets
            return False

        return self._visible(node)[0]


def write_docs(kconfig: kconfiglib.Kconfig, visibility: ConfigTargetVisibility, filename: str) -> None:
    """
    Note: writing .rst documentation ignores the current value
    of any items. ie the --config option can be ignored.
    (However at time of writing it still needs to be set to something...)
    """
    reverse_deps = _cache_reverse_dependency_mappings(kconfig)
    with open(filename, "w") as f:
        for node in kconfig.node_iter():
            write_menu_item(f, node, visibility, kconfig, reverse_deps)


def node_is_menu(node):
    try:
        return node.item in [kconfiglib.MENU, kconfiglib.COMMENT] or node.is_menuconfig
    except AttributeError:
        return False  # not all MenuNodes have is_menuconfig for some reason


def get_breadcrumbs(node):
    # this is a bit wasteful as it recalculates each time, but still...
    result = []
    node = node.parent
    while node.parent:
        if node.prompt:
            result = [f":ref:`{get_link_anchor(node)}`"] + result
        node = node.parent
    return " > ".join(result)


def get_link_anchor(node):
    try:
        return f"CONFIG_{node.item.name}"
    except AttributeError:
        assert node_is_menu(node)  # only menus should have no item.name

    # for menus, build a link anchor out of the parents
    result = []
    while node.parent:
        if node.prompt:
            result = [re.sub(r"[^a-zA-z0-9]+", "-", node.prompt[0])] + result
        node = node.parent
    result = "-".join(result).lower()
    return result


def get_heading_level(node):
    result = INITIAL_HEADING_LEVEL
    node = node.parent
    while node.parent:
        result += 1
        if result == MAX_HEADING_LEVEL:
            return MAX_HEADING_LEVEL
        node = node.parent
    return result


def format_rest_text(text, indent):
    # Format an indented text block for use with ReST
    text = indent + text.replace("\n", "\n" + indent)
    # Escape some characters which are inline formatting in ReST
    text = text.replace("*", "\\*")
    text = text.replace("_", "\\_")
    # replace absolute links to documentation by relative ones
    text = re.sub(
        r"https://docs.espressif.com/projects/esp-idf/\w+/\w+/(.+)\.html",
        r":doc:`../\1`",
        text,
    )
    text += "\n"
    return text


def _references_unresolved_env(expr, target_env_var):
    """
    True if expr still contains an unexpanded ${...} that is not the docs target, i.e. a value derived from an
    environment variable that was unset at parse time. Macros ($(...)) and env vars set at build time are expanded
    during parsing and leave no ${...}, so they are not matched.
    """
    if type(expr) is tuple:
        return any(_references_unresolved_env(sub, target_env_var) for sub in expr[1:])
    return type(expr) is kconfiglib.Symbol and "${" in expr.name and target_env_var not in expr.name


def _is_undefined_reference(sym):
    """
    True if sym is referenced but never defined for this target and is a genuine
    reference (not a numeric literal or quoted constant). This also covers a bogus
    `depends on <choice_name>`: a choice name is not a value, so referencing it just
    creates a node-less stub, and kconfiglib itself reports it as undefined.
    Such a symbol is a hard n on every target: it has no prompt, no default, and a
    type-less symbol cannot be promoted by select/imply, so its dependents can be
    hidden.
    """
    return (
        type(sym) is kconfiglib.Symbol
        and not sym.is_constant
        and not sym.nodes
        and not kconfiglib._looks_like_number(sym.name)
    )


def _minimize_expr(expr, visibility, kconfig):
    """
    Simplify expr for the current docs target and visibility.

    Folds operands that are constant in this pass: target-constant symbols (see
    ConfigTargetVisibility._is_item_target_constant) evaluate to y/n, and a
    comparison whose operands are all target-constant is evaluated to y/n too.
    AND/OR/NOT and simple equalities are then constant-folded so e.g.
    IDF_TARGET_CHIPA && FOO becomes FOO. Symbols the user can still influence are
    left intact so relations like FOO < 2 remain meaningful.
    """
    y = kconfig.y
    n = kconfig.n

    if type(expr) is tuple:
        if expr[0] == kconfiglib.NOT:
            new_expr = _minimize_expr(expr[1], visibility, kconfig)
            if new_expr is n:
                return y
            if new_expr is y:
                return n
            # Operand is still a free variable the user can flip (e.g. !USER_OPTION); keep the negation.
            return (kconfiglib.NOT, new_expr)
        else:
            if expr[0] in _COMPARISON_OPS and visibility._expr_is_target_constant(expr):
                # Relation over target-constant operands has a fixed truth value for this target
                # (e.g. IDF_TARGET="esp32p4" or a promptless, target-derived string/int).
                return y if kconfiglib.expr_value(expr) else n
            new_expr1 = _minimize_expr(expr[1], visibility, kconfig)
            new_expr2 = _minimize_expr(expr[2], visibility, kconfig)
            if expr[0] == kconfiglib.AND:
                if new_expr1 is n or new_expr2 is n:
                    return n
                if new_expr1 is y:
                    return new_expr2
                if new_expr2 is y:
                    return new_expr1
            elif expr[0] == kconfiglib.OR:
                if new_expr1 is y or new_expr2 is y:
                    return y
                if new_expr1 is n:
                    return new_expr2
                if new_expr2 is n:
                    return new_expr1
            elif expr[0] == kconfiglib.EQUAL:
                if type(new_expr1) is not type(new_expr2):
                    return n
                if new_expr1 == new_expr2:
                    return y
            elif expr[0] == kconfiglib.UNEQUAL:
                if type(new_expr1) is not type(new_expr2):
                    return y
                if new_expr1 != new_expr2:
                    return n
            else:  # <, <=, >, >=
                if type(new_expr1) is not type(new_expr2):
                    return n  # e.g "True < 2"
                # Do not fold via expr_value: invisible ints may be unset during
                # docs generation, and the condition should still be shown.

            return (expr[0], new_expr1, new_expr2)

    # Change bool symbols whose value the user cannot change for current target to their actual y/n value. Non-bools
    # are never folded here (their str/int value is not a truth value); target-constant non-bools are handled inside
    # comparisons above. User-toggleable bools are kept so the condition still reflects what the user can influence.
    if (
        type(expr) is kconfiglib.Symbol
        and expr.orig_type == kconfiglib.BOOL
        and visibility._is_item_target_constant(expr)
    ):
        return y if kconfiglib.expr_value(expr) else n

    # A genuinely undefined symbol is a hard n for every target. It is UNKNOWN-typed so the bool fold above skips it;
    # collapse it here so dependents on an omitted symbol (e.g. a SOC_* cap absent for this chip) are hidden. Numeric
    # literals and quoted constants are node-less too, so they are excluded (see _is_undefined_reference).
    if _is_undefined_reference(expr):
        return n

    return expr


def _cache_reverse_dependency_mappings(kconfig):
    """
    Build "target -> [(source, ...)]" mappings for strong reverse dependencies (select and set).
    Building this mapping once and passing it to write_menu_item is more efficient than building it for each menu item.
    """
    selected_mapping = {}
    set_mapping = {}
    for src in kconfig.unique_defined_syms:
        for target, cond in src.selects:
            selected_mapping.setdefault(target, []).append((src, cond))
        for target, value, cond in src.sets:
            set_mapping.setdefault(target, []).append((src, value, cond))
    return selected_mapping, set_mapping


def _remove_deps_from_expr(expr, deps, y):
    """
    Return expr with deps replaced by y (no folding).

    Select/set conditions include the source's depends on; that part is
    redundant next to the source's "Symbol can be set when". AND/OR/NOT simplification
    is left to _minimize_expr (so e.g. FOO && y becomes FOO there).

    NOTE: deps is generally an expression, not a standalone symbol.
    """
    if expr is deps or expr == deps:
        return y
    if type(expr) is tuple:
        if expr[0] == kconfiglib.NOT:
            return (kconfiglib.NOT, _remove_deps_from_expr(expr[1], deps, y))
        return (
            expr[0],
            _remove_deps_from_expr(expr[1], deps, y),
            _remove_deps_from_expr(expr[2], deps, y),
        )
    return expr


def _prepare_cond(cond, visibility, kconfig, direct_deps=None):
    """
    Prepare a condition for documentation:
    * Remove direct dependencies (depends on) from the condition (described in "Symbol can be set when")
    * Minimize the condition (e.g. FOO && y becomes FOO)


    Returns None if the dependency never applies for this target, y if it always
    applies (after optional direct_deps removal), or the remaining expression.
    """
    if direct_deps is not None:
        cond = _remove_deps_from_expr(cond, direct_deps, kconfig.y)
    cond = _minimize_expr(cond, visibility, kconfig)
    if cond is kconfig.n:
        return None
    return cond


def _is_bool_sym(expr):
    """
    True if expr is a bool symbol, i.e. one that reads as "enabled"/"disabled"
    in a condition. The y/n constants are the only bool constants and are always
    folded away by _minimize_expr before this is reached.
    """
    return type(expr) is kconfiglib.Symbol and expr.orig_type == kconfiglib.BOOL


def _parenthesize_cond(expr, wrap_op, sc_str_fn):
    """
    _cond_to_doc_str() helper mirroring kconfiglib._parenthesize: wrap expr in
    parentheses when its top operator is wrap_op.
    """
    if type(expr) is tuple and expr[0] is wrap_op:
        return f"({_cond_to_doc_str(expr, sc_str_fn)})"
    return _cond_to_doc_str(expr, sc_str_fn)


def _cond_to_doc_str(expr, sc_str_fn):
    """
    Render a condition (assignability, range/default, select/set) for the docs.

    A bare bool symbol is shown as "<sym> is enabled" and its negation as
    "<sym> is disabled". Boolean operators keep &&/||/! and the same
    parenthesization as kconfiglib.expr_str, so e.g. "(A || B) && C" is
    preserved. Relations (A = B, A < B, ...) are rendered by expr_str.
    """
    if type(expr) is not tuple:
        if _is_bool_sym(expr):
            return f"{sc_str_fn(expr)} is enabled"
        return sc_str_fn(expr)

    op = expr[0]
    if op == kconfiglib.AND:
        return (
            f"{_parenthesize_cond(expr[1], kconfiglib.OR, sc_str_fn)} && "
            f"{_parenthesize_cond(expr[2], kconfiglib.OR, sc_str_fn)}"
        )
    if op == kconfiglib.OR:
        return (
            f"{_parenthesize_cond(expr[1], kconfiglib.AND, sc_str_fn)} || "
            f"{_parenthesize_cond(expr[2], kconfiglib.AND, sc_str_fn)}"
        )
    if op == kconfiglib.NOT:
        inner = expr[1]
        if _is_bool_sym(inner):
            return f"{sc_str_fn(inner)} is disabled"
        if type(inner) is tuple:
            return f"!({_cond_to_doc_str(inner, sc_str_fn)})"
        return f"!{sc_str_fn(inner)}"
    # Relation (=, !=, <, <=, >, >=)
    return kconfiglib.expr_str(expr, sc_str_fn)


def _format_sym_value(val, expr_str_fn):
    """
    Format a symbol or constant value to the format used in the documentation.
    """
    if type(val) is kconfiglib.Symbol:
        if not val.is_constant and val.nodes:
            return expr_str_fn(val)
        d = val.str_value
    else:
        d = str(val)
    if d in ("y", "Y"):
        return "Enabled"
    if d in ("n", "N"):
        return "Disabled"
    if re.search(r"[^0-9a-fA-F]", d):
        return f'"{d}"'
    return d


def _write_list_section(f, title, lines):
    """
    Helper to write a list section with the given title and lines
    """
    if not lines:
        return
    f.write(f"{INDENT}{title}:\n")
    f.write("\n".join(lines))
    f.write("\n\n")


def _conds_equal(a, b):
    """
    Structural equality for minimized conditions (Symbol / tuple / y / n).
    """
    if a is b or a == b:
        return True
    if type(a) is tuple and type(b) is tuple and len(a) == len(b):
        return all(_conds_equal(x, y) for x, y in zip(a, b))
    return False


def _filter_possibly_applicable_rows(items, visibility, kconfig, direct_deps=None):
    """
    Yield (item, cond) rows from a default/range list that may still apply.

    Drops entries that are n for this target, skips duplicate conditions, keeps
    open conditions (e.g. FOO), and stops after the first always-true (y) entry
    — later rows are shadowed under Kconfig's first-true-wins rules.
    """
    seen = []
    y = kconfig.y
    for item, cond in items:
        display = _prepare_cond(cond, visibility, kconfig, direct_deps=direct_deps)
        if display is None:
            continue
        if any(_conds_equal(display, prev) for prev in seen):
            continue
        yield item, display
        seen.append(display)
        if display is y:
            break


def _sym_has_visible_prompted_node(sym, visibility):
    """
    True if sym has a prompted node that is visible for this docs target.

    Choice members are visible when their parent choice entry is visible; other
    nodes when the node itself is visible. Shared by _has_docs_anchor (does the
    symbol get an anchor) and _source_sym_may_force (may a source force a value)
    so the two policies stay in sync.
    """
    for node in sym.nodes:
        if not node.prompt:
            continue
        # Choice members get anchors under the parent choice entry
        parent = node.parent
        if parent is not None and type(parent.item) is kconfiglib.Choice:
            if visibility.visible(parent):
                return True
            continue
        if visibility.visible(node):
            return True
    return False


def _has_docs_anchor(sym, visibility):
    """
    True if gen_kconfig_doc writes a Sphinx anchor for this symbol.

    Promptless symbols and options invisible for the target are never written,
    so :ref: must not point at them.
    """
    if type(sym) is not kconfiglib.Symbol or sym.is_constant or not sym.nodes:
        return False
    return _sym_has_visible_prompted_node(sym, visibility)


def _source_sym_may_force(src, visibility):
    """
    True if src should appear as a Force-set by source for this docs target.

    User-visible (documented) sources may be enabled by the user. Promptless or
    target-invisible sources are treated as constant: only keep them when they
    evaluate to y for the current target.
    """
    if type(src) is not kconfiglib.Symbol:
        return False
    if _sym_has_visible_prompted_node(src, visibility):
        return True
    return bool(kconfiglib.expr_value(src))


def write_menu_item(f, node, visibility, kconfig, reverse_deps):
    """
    Write a docs block for one visible menu tree node.

    Skips choice symbols (documented under the parent choice), target-invisible
    nodes, and excluded menu names. Comments are never written (always treated
    as invisible).

    Common for written nodes: Sphinx anchor, heading, optional help text.

    Symbol:
        Prompt, "Found in" breadcrumbs, optional "Symbol can be set when",
        Range, Default value, forward select/set effects, and reverse
        select/set ("Following symbols affect...").

    Choice:
        Heading from the choice name or prompt, "Available options" list with
        per-option anchors, CONFIG_ names, and help.

    Menu (including menuconfig):
        Heading from the prompt (or CONFIG_ name for menuconfig symbols), then
        a sorted "Contains" list of links to visible children. menuconfig
        symbols also get the Symbol sections above.
    """

    def is_choice_member(node):
        """
        True if node is an option inside a choice (written with the parent choice).
        """
        return type(node.parent.item) is kconfiglib.Choice

    if is_choice_member(node) or not visibility.visible(node):
        return

    try:
        name = node.item.name
    except AttributeError:
        name = None

    is_menu = node_is_menu(node)

    if is_menu and node.prompt[0] in EXCLUDED_MENU_NAMES:
        return

    # Heading
    if name:
        title = f"CONFIG_{name}"
    else:
        # if no symbol name, use the prompt as the heading
        title = node.prompt[0]

    f.write(f".. _{get_link_anchor(node)}:\n\n")
    f.write(f"{title}\n")
    f.write(HEADING_SYMBOLS[get_heading_level(node)] * len(title))
    f.write("\n\n")

    if name:
        f.write(f"{INDENT}{node.prompt[0]}\n\n")
        f.write(f"{INDENT}:emphasis:`Found in:` {get_breadcrumbs(node)}\n\n")

    try:
        if node.help:
            # Help text normally contains newlines, but spaces at the beginning of
            # each line are stripped by kconfiglib. We need to re-indent the text
            # to produce valid ReST.
            f.write(format_rest_text(node.help, INDENT))
            f.write("\n")
    except AttributeError:
        pass  # No help

    if type(node.item) is kconfiglib.Choice:
        f.write(f"{INDENT}Available options:\n\n")
        choice_node = node.list
        while choice_node:
            # Format available options as a list
            # First, link anchor for this option
            f.write(f"{INDENT * 2}  .. _{get_link_anchor(choice_node)}:\n\n")
            # Then, option itself, as a list item
            prompt = choice_node.prompt[0]
            prefix = node.kconfig.config_prefix
            opt = choice_node.item.name
            f.write(f"{INDENT * 2}- {prompt:<20} ({prefix}{opt})\n")
            if choice_node.help:
                HELP_INDENT = INDENT * 2
                fmt_help = format_rest_text(choice_node.help, "  " + HELP_INDENT)
                f.write(f"{HELP_INDENT}  \n{fmt_help}\n")
            choice_node = choice_node.next
            f.write("\n")

        f.write("\n\n")

    if type(node.item) is kconfiglib.Symbol:

        def _doc_str(sc):
            """
            Returns a string representation of a symbol or constant for documentation with :ref: if possible.
            """
            if sc.is_constant or not sc.nodes:
                return f"{sc.name}"
            opt_name = f"{sc.kconfig.config_prefix}{sc.name}"
            if not _has_docs_anchor(sc, visibility):
                return opt_name
            if sc.choice:
                # link targets not associated with a section cannot be referenced without providing the title
                # https://github.com/sphinx-doc/sphinx/issues/9993
                return f":ref:`{opt_name}<{opt_name}>`"
            return f":ref:`{opt_name}`"

        def _doc_if_cond(cond):
            """
            Returns " if <condition>" formatted for documentation if there is a condition.
            """
            if cond is kconfig.y:
                return ""
            return f" if {_cond_to_doc_str(cond, _doc_str)}"

        sym = node.item

        # During finalization, Kconfig._propagate_deps() rewrites node.prompt[1]
        # to "original if-cond AND visible_if AND dep", where dep is the symbol's
        # own "depends on" plus deps propagated from parent menus/choices/if, and
        # visible_if is the "visible if" of parent menus. So the prompt condition
        # already captures everything that gates assignability.
        can_be_set_when = _prepare_cond(node.prompt[1], visibility, kconfig)
        if can_be_set_when is not None and can_be_set_when is not kconfig.y:
            _write_list_section(
                f, "Symbol can be set when", [f"{INDENT * 2}{_cond_to_doc_str(can_be_set_when, _doc_str)}"]
            )

        # Strip direct_dep from range/default conditions: it is already covered by
        # "Symbol can be set when". That also turns "if IDF_TARGET_X" (+ depends) into y
        # for the active target so the matching entry shadows the fallback.
        range_strs = []
        for (low, high), cond in _filter_possibly_applicable_rows(
            [((lo, hi), c) for lo, hi, c in sym.ranges],
            visibility,
            kconfig,
            direct_deps=sym.direct_dep,
        ):
            range_strs.append(f"{INDENT * 2}- from {low.str_value} to {high.str_value}{_doc_if_cond(cond)}")
        _write_list_section(f, "Range", range_strs)

        default_strs = []
        for default, cond in _filter_possibly_applicable_rows(
            sym.defaults, visibility, kconfig, direct_deps=sym.direct_dep
        ):
            d = _format_sym_value(default, _doc_str)
            default_strs.append(f"{INDENT * 2}- {d}{_doc_if_cond(cond)}")
        _write_list_section(f, "Default value", default_strs)

        when_enabled = []
        for target, cond in sym.selects:
            c = _prepare_cond(cond, visibility, kconfig, direct_deps=sym.direct_dep)
            if c is None:
                continue
            when_enabled.append(f"{INDENT * 2}- forcefully enables {_doc_str(target)}{_doc_if_cond(c)}")
        for target, value, cond in sym.sets:
            c = _prepare_cond(cond, visibility, kconfig, direct_deps=sym.direct_dep)
            if c is None:
                continue
            when_enabled.append(
                f"{INDENT * 2}- sets {_doc_str(target)} to {_format_sym_value(value, _doc_str)}{_doc_if_cond(c)}"
            )
        _write_list_section(f, "This symbol affects the value of following symbols", when_enabled)

        forced_by = []
        selected_by, set_by = reverse_deps
        for src, cond in selected_by.get(sym, []):
            if not _source_sym_may_force(src, visibility):
                continue
            c = _prepare_cond(cond, visibility, kconfig, direct_deps=src.direct_dep)
            if c is None:
                continue
            forced_by.append(f"{INDENT * 2}- forcefully enabled by {_doc_str(src)}{_doc_if_cond(c)}")
        for src, value, cond in set_by.get(sym, []):
            if not _source_sym_may_force(src, visibility):
                continue
            c = _prepare_cond(cond, visibility, kconfig, direct_deps=src.direct_dep)
            if c is None:
                continue
            forced_by.append(
                f"{INDENT * 2}- set by {_doc_str(src)} to {_format_sym_value(value, _doc_str)}{_doc_if_cond(c)}"
            )
        _write_list_section(f, "Following symbols affect the value of this symbol", forced_by)

    if is_menu:
        # enumerate links to child items
        child_list = []
        child = node.list
        while child:
            if (
                not is_choice_member(child)
                and child.prompt
                and visibility.visible(child)
                and child.prompt[0] not in EXCLUDED_MENU_NAMES
            ):
                child_list.append((child.prompt[0], get_link_anchor(child)))
            child = child.next
        if len(child_list) > 0:
            f.write("Contains:\n\n")
            sorted_child_list = sorted(child_list, key=lambda pair: pair[0].lower())
            ref_list = [f"- :ref:`{anchor}`" for _, anchor in sorted_child_list]
            f.write("\n".join(ref_list))
            f.write("\n\n")
