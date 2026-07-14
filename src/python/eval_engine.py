"""
eval_engine.py -- baseline engine using Python eval() per row.

This is the "second baseline" the assignment explicitly asks for: expect it
to be slow (interpreter dispatch + a Python function call per row, twice per
row for conditionals) -- that is the point of including it in the benchmark.

Security: formula strings never reach eval() unvalidated. Every formula goes
through formula_parser.compile_formula() first, which walks the AST against
the SEMANTICS.md whitelist grammar and raises before anything unsafe could
be compiled. eval() itself runs with SAFE_GLOBALS (__builtins__ emptied) as
defense in depth on top of that validation.

Usage: python -m src.python.eval_engine [--persist=full]
"""

import argparse
import math
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from src.python import persistence
from src.python.formula_parser import SAFE_GLOBALS, compile_formula

METHOD = "python_eval"


def _is_bad(x) -> bool:
    return x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def _eval_row(code, loc) -> float | None:
    try:
        val = eval(code, SAFE_GLOBALS, loc)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    return None if _is_bad(val) else float(val)


def run_formula(formula: dict, data_id, a, b, c, d, sample_ids, *, persist_full: bool) -> None:
    targil_id = formula["targil_id"]
    is_conditional = formula["tnai"] is not None

    t0 = time.perf_counter()
    code_value = compile_formula(formula["targil"], is_condition=False)
    code_cond = compile_formula(formula["tnai"], is_condition=True) if is_conditional else None
    code_false = compile_formula(formula["targil_false"], is_condition=False) if is_conditional else None
    compile_ms = (time.perf_counter() - t0) * 1000.0

    n = len(a)
    results = np.empty(n, dtype=np.float64)

    t0 = time.perf_counter()
    for i in range(n):
        loc = {"a": a[i], "b": b[i], "c": c[i], "d": d[i]}
        if is_conditional:
            cond = _eval_row(code_cond, loc)
            if cond is None:
                # condition itself hit a domain error -> overall row is NULL
                # (SEMANTICS.md section 5) -- never silently fall through to
                # the false branch, since NaN comparisons are all falsy.
                val = None
            else:
                val = _eval_row(code_value if cond else code_false, loc)
        else:
            val = _eval_row(code_value, loc)
        results[i] = np.nan if val is None else val
    eval_ms = (time.perf_counter() - t0) * 1000.0

    null_mask = np.isnan(results)
    null_count = int(np.count_nonzero(null_mask))
    checksum = float(np.sum(results[~null_mask])) if null_count < n else 0.0

    conn = persistence.connect()
    try:
        if persist_full:
            persist_ms = persistence.write_results_full(
                conn, targil_id=targil_id, method=METHOD, data_id=data_id, results=results
            )
        else:
            # data_id is contiguous 1..N ascending, so data_id value `did`
            # sits at array index `did - 1` -- must not use `did` itself as
            # an array index (that silently persists the wrong, off-by-one
            # row while still looking internally consistent).
            results_by_id = {did: (None if null_mask[did - 1] else float(results[did - 1])) for did in sample_ids.tolist()}
            persist_ms = persistence.write_results_sample(
                conn, targil_id=targil_id, method=METHOD, sample_ids=sample_ids, results_by_id=results_by_id
            )

        run_time = compile_ms + eval_ms + persist_ms
        persistence.write_log(
            conn,
            targil_id=targil_id,
            method=METHOD,
            run_time=run_time,
            rows_processed=n,
            compile_ms=compile_ms,
            eval_ms=eval_ms,
            persist_ms=persist_ms,
            checksum=checksum,
            null_count=null_count,
        )
    finally:
        conn.close()

    print(
        f"  targil {targil_id:>2}: compile={compile_ms:8.2f}ms  eval={eval_ms:9.2f}ms  "
        f"persist={persist_ms:8.2f}ms  nulls={null_count:>7}  checksum={checksum:.6f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persist", choices=["sample", "full"], default="sample")
    args = parser.parse_args()
    persist_full = args.persist == "full"

    conn = persistence.connect()
    try:
        formulas = persistence.fetch_formulas(conn)
        print(f"Loading {persistence.TOTAL_ROWS:,} rows of t_data...")
        data_id, a, b, c, d = persistence.fetch_all_data(conn)
        sample_ids = persistence.fetch_sample_ids(conn)
    finally:
        conn.close()

    print(f"[{METHOD}] evaluating {len(formulas)} formulas x {len(a):,} rows (persist={args.persist})")
    start = time.perf_counter()
    for formula in formulas:
        run_formula(formula, data_id, a, b, c, d, sample_ids, persist_full=persist_full)
    total = time.perf_counter() - start
    print(f"[{METHOD}] done in {total:.2f}s")


if __name__ == "__main__":
    main()
