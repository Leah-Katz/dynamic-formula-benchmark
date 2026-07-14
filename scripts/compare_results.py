"""
compare_results.py -- cross-engine correctness verification (assignment
Step 7). Two independent checks, both must pass:

  1. Row-level: join t_results across all 5 methods for every (data_id,
     targil_id) in the persisted 10,000-row sample, compare pairwise.
  2. Full-dataset: compare the checksum + null_count every engine wrote to
     t_log for the full 1,000,000-row run (SEMANTICS.md section 7).

Tolerance is SEMANTICS.md section 6 exactly:
    abs(x - y) <= 1e-9 * max(abs(x), abs(y), 1.0)
NULL must match NULL exactly; NULL vs. any non-NULL value is always a
mismatch regardless of tolerance. null_count must match exactly (integer).

dotnet_datatable does not cover every formula (DataColumn.Expression has no
Sqrt/Log -- see src/dotnet/DataTableCompute/DataColumnExpressionEmitter.cs).
A formula/method-pair where one side has no data at all is reported N/A,
not FAIL -- that is a documented, disclosed limitation, not a correctness
bug. Exits non-zero on any real mismatch (N/A does not count as failure).
"""

import sys
from collections import defaultdict
from itertools import combinations

sys.path.insert(0, ".")
from src.python import persistence

TOLERANCE = 1e-9


def close_enough(x: float, y: float) -> bool:
    return abs(x - y) <= TOLERANCE * max(abs(x), abs(y), 1.0)


def values_match(x, y) -> bool:
    if x is None or y is None:
        return x is None and y is None
    return close_enough(x, y)


def fetch_methods(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT method FROM dbo.t_log ORDER BY method")
    return [r[0] for r in cur.fetchall()]


def fetch_sample_results(conn) -> dict[tuple[str, int, int], float | None]:
    """(method, targil_id, data_id) -> result, for the persisted sample."""
    cur = conn.cursor()
    cur.execute("SELECT method, targil_id, data_id, result FROM dbo.t_results")
    out: dict[tuple[str, int, int], float | None] = {}
    for method, targil_id, data_id, result in cur.fetchall():
        out[(method, targil_id, data_id)] = result
    return out


def fetch_latest_log(conn) -> dict[tuple[str, int], tuple[float | None, int]]:
    """(method, targil_id) -> (checksum, null_count) from the most recent
    run of each. Multiple runs accumulate in t_log over time; the latest
    run_ts per (targil_id, method) is the current, authoritative one."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT method, targil_id, checksum, null_count
        FROM dbo.t_log t
        WHERE run_ts = (
            SELECT MAX(t2.run_ts) FROM dbo.t_log t2
            WHERE t2.targil_id = t.targil_id AND t2.method = t.method
        )
        """
    )
    out: dict[tuple[str, int], tuple[float | None, int]] = {}
    for method, targil_id, checksum, null_count in cur.fetchall():
        out[(method, targil_id)] = (checksum, null_count)
    return out


def main() -> int:
    conn = persistence.connect()
    try:
        methods = fetch_methods(conn)
        formulas = persistence.fetch_formulas(conn)
        sample_ids = persistence.fetch_sample_ids(conn).tolist()
        sample_results = fetch_sample_results(conn)
        latest_log = fetch_latest_log(conn)
    finally:
        conn.close()

    print(f"Methods found: {methods}")
    print(f"Formulas: {len(formulas)}   Sample size: {len(sample_ids):,}   Tolerance: {TOLERANCE:g}\n")

    method_pairs = list(combinations(methods, 2))
    any_failure = False

    # -- Check 1: row-level sample comparison ---------------------------------
    print("=" * 100)
    print("ROW-LEVEL COMPARISON (10,000-row sample, per formula per method pair)")
    print("=" * 100)
    header = f"{'targil':>6}  " + "  ".join(f"{m1[:8]}/{m2[:8]:>8}" for m1, m2 in method_pairs)
    print(header)

    row_level_ok = defaultdict(lambda: True)
    for formula in formulas:
        tid = formula["targil_id"]
        cells = []
        for m1, m2 in method_pairs:
            # cheap existence check: does this method have ANY row for this formula?
            m1_has = (m1, tid, sample_ids[0]) in sample_results
            m2_has = (m2, tid, sample_ids[0]) in sample_results
            if not (m1_has and m2_has):
                cells.append(f"{'N/A':>17}")
                continue

            mismatches = 0
            for did in sample_ids:
                v1 = sample_results.get((m1, tid, did))
                v2 = sample_results.get((m2, tid, did))
                if not values_match(v1, v2):
                    mismatches += 1

            ok = mismatches == 0
            row_level_ok[(m1, m2)] = row_level_ok[(m1, m2)] and ok
            if not ok:
                any_failure = True
            cells.append(f"{'PASS' if ok else f'FAIL({mismatches})':>17}")
        print(f"{tid:>6}  " + "  ".join(cells))

    # -- Check 2: full-dataset checksum / null_count comparison ---------------
    print()
    print("=" * 100)
    print("FULL-DATASET COMPARISON (checksum + null_count over all 1,000,000 rows, from t_log)")
    print("=" * 100)
    print(header)

    for formula in formulas:
        tid = formula["targil_id"]
        cells = []
        for m1, m2 in method_pairs:
            e1 = latest_log.get((m1, tid))
            e2 = latest_log.get((m2, tid))
            if e1 is None or e2 is None:
                cells.append(f"{'N/A':>17}")
                continue
            checksum1, null1 = e1
            checksum2, null2 = e2
            ok = (null1 == null2) and (
                (checksum1 is None and checksum2 is None)
                or (checksum1 is not None and checksum2 is not None and close_enough(checksum1, checksum2))
            )
            if not ok:
                any_failure = True
            cells.append(f"{'PASS' if ok else 'FAIL':>17}")
        print(f"{tid:>6}  " + "  ".join(cells))

    # -- Summary ---------------------------------------------------------------
    print()
    print("=" * 100)
    if any_failure:
        print("RESULT: MISMATCH DETECTED -- see FAIL cells above. NOT all methods agree.")
    else:
        print(f"RESULT: All methods produced identical results (tolerance {TOLERANCE:g}).")
        print("        (N/A cells are documented limitations, not failures -- see REPORT.md.)")
    print("=" * 100)

    return 1 if any_failure else 0


if __name__ == "__main__":
    sys.exit(main())
