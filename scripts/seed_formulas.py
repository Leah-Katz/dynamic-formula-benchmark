"""
seed_formulas.py -- populate t_targil with the formula catalog.

Every formula string is validated against the shared grammar in
formula_parser.py (SEMANTICS.md section 2) *before* insertion -- this both
catches typos in the catalog itself and proves the parser accepts every
formula the engines will actually be asked to evaluate. `^` is stored
literally as exponentiation syntax; each engine translates it to its own
operator/function at evaluation time (SEMANTICS.md section 3).
"""

import sys

import pyodbc

sys.path.insert(0, ".")
from config import CONNECTION_STRING
from src.python.formula_parser import validate

# (targil_id, targil, tnai, targil_false)
# tnai is None for plain formulas; when set, targil/targil_false are the
# true/false branches of the condition.
FORMULAS = [
    # -- Simple --------------------------------------------------------
    (1, "a + b", None, None),
    (2, "c * 2", None, None),
    (3, "b - a", None, None),
    (4, "d / 4", None, None),
    # -- Complex ---------------------------------------------------------
    (5, "(a + b) * 8", None, None),
    (6, "sqrt(c^2 + d^2)", None, None),
    (7, "log(b) + c", None, None),
    (8, "abs(d - b)", None, None),
    # -- Conditional -------------------------------------------------------
    (9, "b * 2", "a > 5", "b / 2"),
    (10, "a + 1", "b < 10", "d - 1"),
    (11, "1", "a == c", "0"),
    # -- Stress (deeply nested / condition with complex sub-expressions) ---
    (12, "sqrt(abs((a + b) * (c - d)) + pow(a, 2))", None, None),
    (13, "(a + b + c + d) / 4", "sqrt(a^2 + b^2) > c", "max(a, b)"),
]


def validate_catalog() -> None:
    for targil_id, targil, tnai, targil_false in FORMULAS:
        validate(targil, is_condition=False)
        if tnai is not None:
            validate(tnai, is_condition=True)
            validate(targil_false, is_condition=False)
    print(f"All {len(FORMULAS)} formulas pass grammar validation (SEMANTICS.md section 2).")


def main() -> None:
    validate_catalog()

    conn = pyodbc.connect(CONNECTION_STRING)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.t_log")
        cur.execute("DELETE FROM dbo.t_results")
        cur.execute("DELETE FROM dbo.t_targil")
        cur.executemany(
            "INSERT INTO dbo.t_targil (targil_id, targil, tnai, targil_false) VALUES (?, ?, ?, ?)",
            FORMULAS,
        )
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM dbo.t_targil")
        count = cur.fetchone()[0]
        assert count == len(FORMULAS), f"expected {len(FORMULAS)} formulas, found {count}"
        print(f"Inserted {count} formulas into t_targil.")

        plain = sum(1 for f in FORMULAS if f[2] is None)
        conditional = len(FORMULAS) - plain
        print(f"  plain: {plain}, conditional: {conditional}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
