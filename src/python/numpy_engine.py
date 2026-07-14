"""
numpy_engine.py -- vectorized NumPy engine: translate each formula into a
NumPy expression once, then evaluate it over the entire 1,000,000-element
column arrays in a handful of vectorized calls (no per-row Python loop).
This is the "compile once (to NumPy source), execute over the whole column"
strategy -- expect it to be dramatically faster than eval_engine.py.

Security: identical to eval_engine.py -- every formula goes through
formula_parser.validate() (AST whitelist walk) before any NumPy source is
emitted or eval()'d. The translated source only ever references np.* and
the four known column arrays, never anything derived from the raw string.

Usage: python -m src.python.numpy_engine [--persist=full]
"""

import argparse
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from src.python import persistence
from src.python.formula_parser import to_numpy_condition_sides, to_numpy_expr

METHOD = "python_numpy"

_OP_FUNCS = {
    ">": np.greater,
    "<": np.less,
    ">=": np.greater_equal,
    "<=": np.less_equal,
    "==": np.equal,
    "!=": np.not_equal,
}


def _finalize(arr: np.ndarray) -> np.ndarray:
    """Catch-all domain-error rule (SEMANTICS.md section 4): NaN/Inf -> NULL
    (np.nan sentinel), applied once at the end rather than pre-validating
    every sub-operation."""
    bad = ~np.isfinite(arr)
    if bad.any():
        arr = arr.copy()
        arr[bad] = np.nan
    return arr


def run_formula(formula: dict, data_id, a, b, c, d, sample_ids, *, persist_full: bool) -> None:
    targil_id = formula["targil_id"]
    is_conditional = formula["tnai"] is not None
    ns = {"np": np, "a": a, "b": b, "c": c, "d": d}

    t0 = time.perf_counter()
    value_src = to_numpy_expr(formula["targil"])
    if is_conditional:
        left_src, op, right_src = to_numpy_condition_sides(formula["tnai"])
        false_src = to_numpy_expr(formula["targil_false"])
    compile_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    with np.errstate(all="ignore"):
        if is_conditional:
            left = eval(left_src, {"__builtins__": {}}, ns)
            right = eval(right_src, {"__builtins__": {}}, ns)
            cond_invalid = ~(np.isfinite(left) & np.isfinite(right))
            cond = _OP_FUNCS[op](left, right)

            true_vals = _finalize(np.asarray(eval(value_src, {"__builtins__": {}}, ns), dtype=np.float64))
            false_vals = _finalize(np.asarray(eval(false_src, {"__builtins__": {}}, ns), dtype=np.float64))

            result = np.where(cond, true_vals, false_vals)
            result = np.where(cond_invalid, np.nan, result)
        else:
            result = np.asarray(eval(value_src, {"__builtins__": {}}, ns), dtype=np.float64)
            result = _finalize(result)
    eval_ms = (time.perf_counter() - t0) * 1000.0

    null_mask = np.isnan(result)
    null_count = int(np.count_nonzero(null_mask))
    checksum = float(np.sum(result[~null_mask])) if null_count < len(result) else 0.0

    conn = persistence.connect()
    try:
        if persist_full:
            persist_ms = persistence.write_results_full(
                conn, targil_id=targil_id, method=METHOD, data_id=data_id, results=result
            )
        else:
            # data_id is contiguous 1..N in ascending order (see
            # persistence.fetch_all_data), so data_id `did` sits at index
            # `did - 1` -- no need to build a 1M-entry lookup dict just to
            # resolve 10,000 sample ids.
            results_by_id = {
                did: (None if null_mask[did - 1] else float(result[did - 1]))
                for did in sample_ids.tolist()
            }
            persist_ms = persistence.write_results_sample(
                conn, targil_id=targil_id, method=METHOD, sample_ids=sample_ids, results_by_id=results_by_id
            )

        run_time = compile_ms + eval_ms + persist_ms
        persistence.write_log(
            conn,
            targil_id=targil_id,
            method=METHOD,
            run_time=run_time,
            rows_processed=len(result),
            compile_ms=compile_ms,
            eval_ms=eval_ms,
            persist_ms=persist_ms,
            checksum=checksum,
            null_count=null_count,
        )
    finally:
        conn.close()

    print(
        f"  targil {targil_id:>2}: compile={compile_ms:8.3f}ms  eval={eval_ms:9.3f}ms  "
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
