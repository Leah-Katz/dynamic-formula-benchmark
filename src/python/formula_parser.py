"""
Shared formula parser / validator for the Python engines (eval_engine.py,
numpy_engine.py).

Formula strings come from t_targil, i.e. from outside the program's trust
boundary (see SEMANTICS.md section 2). This module is the single place that
decides whether a formula string is safe to evaluate at all. Nothing downstream
(eval_engine.py, numpy_engine.py) is allowed to hand a raw DB string to eval()
or to a NumPy expression builder without going through validate() first.

Design mirrors SEMANTICS.md section 2 exactly:
  - value expression: + - * / ^ (power), unary -, sqrt/log/abs/min/max/pow,
    parens, numeric literals, identifiers a/b/c/d
  - condition expression (tnai only): exactly one comparison between two
    value expressions (> < >= <= == !=), no boolean composition

Validation is a real AST walk (Python's ast module), not a regex, per the
brief. A coarse character whitelist runs first purely as defense in depth
(cheap, catches obvious injection attempts like semicolons/quotes/backticks
before we even bother invoking the parser) -- it is not a substitute for the
AST walk, which is the actual security boundary.
"""

import ast
import math
import re

# Defense-in-depth pre-filter: only characters that could ever legitimately
# appear in a formula per the SEMANTICS.md grammar. Anything else (quotes,
# semicolons, backticks, brackets, @, $, etc.) is rejected before parsing.
_ALLOWED_CHARS = re.compile(r"^[a-zA-Z0-9_.,()+\-*/^<>=!\s]*$")

# The only identifiers a formula may reference -- the four t_data columns.
_ALLOWED_NAMES = {"a", "b", "c", "d"}

# func name -> required argument count, per SEMANTICS.md section 2.1
_ALLOWED_FUNCS = {"sqrt": 1, "log": 1, "abs": 1, "min": 2, "max": 2, "pow": 2}

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
_ALLOWED_COMPARE_OPS = (ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq)

# Namespace eval_engine.py runs the compiled code against. Empty __builtins__
# means `__import__`, `open`, etc. are unreachable even if something slipped
# past validation -- belt and suspenders, not a replacement for validation.
SAFE_GLOBALS = {
    "__builtins__": {},
    "sqrt": math.sqrt,
    "log": math.log,
    "abs": abs,
    "min": min,
    "max": max,
    "pow": pow,
}


class FormulaValidationError(ValueError):
    """Raised when a formula string fails the whitelist grammar in SEMANTICS.md."""


def _preprocess(formula: str) -> str:
    """`^` means exponentiation in our grammar; Python's ast treats it as XOR.
    Translate before parsing so ast.parse sees `**` (ast.Pow) instead."""
    if not _ALLOWED_CHARS.match(formula):
        raise FormulaValidationError(f"formula contains disallowed characters: {formula!r}")
    return formula.replace("^", "**")


def _validate_node(node: ast.AST, *, allow_compare: bool) -> None:
    """Recursively walk the AST, raising on anything outside the grammar.

    allow_compare is True only at the top level of a condition (tnai) --
    conditions are exactly one comparison, so Compare nodes are never
    permitted to appear nested inside a value expression, and value
    expressions are never permitted to contain a Compare themselves.
    """
    if isinstance(node, ast.Expression):
        _validate_node(node.body, allow_compare=allow_compare)

    elif isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise FormulaValidationError(f"operator not allowed: {type(node.op).__name__}")
        _validate_node(node.left, allow_compare=False)
        _validate_node(node.right, allow_compare=False)

    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ast.USub):
            raise FormulaValidationError(f"unary operator not allowed: {type(node.op).__name__}")
        _validate_node(node.operand, allow_compare=False)

    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise FormulaValidationError(f"function not allowed: {ast.dump(node.func)}")
        if node.keywords or getattr(node, "starargs", None) or getattr(node, "kwargs", None):
            raise FormulaValidationError("keyword/star arguments are not allowed")
        expected_argc = _ALLOWED_FUNCS[node.func.id]
        if len(node.args) != expected_argc:
            raise FormulaValidationError(
                f"{node.func.id}() expects {expected_argc} argument(s), got {len(node.args)}"
            )
        for arg in node.args:
            _validate_node(arg, allow_compare=False)

    elif isinstance(node, ast.Compare):
        if not allow_compare:
            raise FormulaValidationError("comparisons are only allowed in a condition (tnai)")
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise FormulaValidationError("only a single comparison is allowed, no chaining")
        if not isinstance(node.ops[0], _ALLOWED_COMPARE_OPS):
            raise FormulaValidationError(f"comparison operator not allowed: {type(node.ops[0]).__name__}")
        _validate_node(node.left, allow_compare=False)
        _validate_node(node.comparators[0], allow_compare=False)

    elif isinstance(node, ast.Name):
        if node.id not in _ALLOWED_NAMES:
            raise FormulaValidationError(f"identifier not allowed: {node.id!r}")

    elif isinstance(node, ast.Constant):
        # bool is a subclass of int in Python -- reject explicitly so
        # "True"/"False" can't sneak in as numeric literals.
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FormulaValidationError(f"literal not allowed: {node.value!r}")

    else:
        raise FormulaValidationError(f"expression type not allowed: {type(node).__name__}")


def validate(formula: str, *, is_condition: bool = False) -> ast.Expression:
    """Parse + validate a formula string against the SEMANTICS.md grammar.

    Returns the validated AST. Raises FormulaValidationError for anything
    outside the whitelist -- callers must not catch this and fall back to
    evaluating the raw string.
    """
    processed = _preprocess(formula)
    try:
        tree = ast.parse(processed, mode="eval")
    except SyntaxError as exc:
        raise FormulaValidationError(f"formula is not valid syntax: {formula!r}") from exc

    if is_condition:
        if not isinstance(tree.body, ast.Compare):
            raise FormulaValidationError("a condition (tnai) must be a single comparison")
    else:
        if isinstance(tree.body, ast.Compare):
            raise FormulaValidationError("a value expression (targil) must not be a comparison")

    _validate_node(tree, allow_compare=is_condition)
    return tree


def compile_formula(formula: str, *, is_condition: bool = False):
    """Validate then compile to a code object, ready for eval() with SAFE_GLOBALS
    and locals {'a': ..., 'b': ..., 'c': ..., 'd': ...}."""
    tree = validate(formula, is_condition=is_condition)
    return compile(tree, filename="<formula>", mode="eval")


# --- NumPy source emission -------------------------------------------------
# Walks the *validated* AST (never the raw string) and emits a NumPy-ready
# Python expression string. Called only after validate() has already
# succeeded, so every node here is known-safe.

_NUMPY_FUNC_MAP = {
    "sqrt": "np.sqrt",
    "log": "np.log",
    "abs": "np.abs",
    "min": "np.minimum",
    "max": "np.maximum",
    "pow": "np.power",
}

_BINOP_SYMBOL = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "**"}
_COMPARE_SYMBOL = {
    ast.Gt: ">",
    ast.Lt: "<",
    ast.GtE: ">=",
    ast.LtE: "<=",
    ast.Eq: "==",
    ast.NotEq: "!=",
}


def _emit_numpy(node: ast.AST) -> str:
    if isinstance(node, ast.Expression):
        return _emit_numpy(node.body)
    if isinstance(node, ast.BinOp):
        return f"({_emit_numpy(node.left)} {_BINOP_SYMBOL[type(node.op)]} {_emit_numpy(node.right)})"
    if isinstance(node, ast.UnaryOp):
        return f"(-{_emit_numpy(node.operand)})"
    if isinstance(node, ast.Call):
        args = ", ".join(_emit_numpy(a) for a in node.args)
        return f"{_NUMPY_FUNC_MAP[node.func.id]}({args})"
    if isinstance(node, ast.Compare):
        op = _COMPARE_SYMBOL[type(node.ops[0])]
        return f"({_emit_numpy(node.left)} {op} {_emit_numpy(node.comparators[0])})"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return repr(float(node.value))
    raise FormulaValidationError(f"cannot emit NumPy source for: {type(node).__name__}")


def to_numpy_expr(formula: str, *, is_condition: bool = False) -> str:
    """Validate then translate to a NumPy-vectorized expression string, e.g.
    'sqrt(c^2 + d^2)' -> '(np.sqrt((c ** 2.0) + (d ** 2.0)))'.
    The returned string references the *column arrays* a/b/c/d directly and
    is meant to be eval()'d once with {'np': numpy, 'a': arr_a, ...}."""
    tree = validate(formula, is_condition=is_condition)
    return _emit_numpy(tree)


def to_numpy_condition_sides(formula: str) -> tuple[str, str, str]:
    """Validate a condition (tnai) and split it into (left_expr, op_symbol,
    right_expr) NumPy source strings, evaluated separately. Needed so the
    NumPy engine can independently check each side for a domain error
    (NaN/Inf) per SEMANTICS.md section 5: if either side of the condition
    itself is undefined, the overall row result is NULL, not a silent
    default to the false branch (NaN comparisons are False in IEEE-754,
    which would otherwise steer such rows into targil_false unnoticed)."""
    tree = validate(formula, is_condition=True)
    cmp = tree.body
    left_src = _emit_numpy(cmp.left)
    right_src = _emit_numpy(cmp.comparators[0])
    op = _COMPARE_SYMBOL[type(cmp.ops[0])]
    return left_src, op, right_src
