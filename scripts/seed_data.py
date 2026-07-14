"""
seed_data.py -- generate and bulk-load the 1,000,000-row t_data dataset.

Bulk-load strategy: pyodbc with `fast_executemany=True`, batched into
transactions of BATCH_SIZE rows each. This stays inside Python (no bcp.exe /
BULK INSERT file-path juggling, no separate CSV artifact to keep in sync with
the schema) and is fast enough for 1M rows -- fast_executemany switches
pyodbc from row-at-a-time RPC calls to a single parameter array bound per
batch, which is what actually makes this take seconds instead of minutes.
Batching (rather than one 1M-row executemany) keeps each transaction's log
footprint small and gives a progress signal; recovery model is SIMPLE so log
growth isn't a correctness risk either way, this is purely about not holding
one giant uncommitted transaction.

Value ranges (see SEMANTICS.md / assignment brief):
  - a  ~ Uniform(0, 10)        -> symmetric around 5, so "a > 5" branches ~50/50
  - b  ~ Uniform(1e-4, 20)     -> strictly positive (log(b) always defined),
                                   symmetric around 10, so "b < 10" branches ~50/50
  - c  ~ Uniform(-10, 10)      -> general range for sqrt(c^2+d^2), log(b)+c, a==c
  - d  ~ Uniform(-10, 10)      -> general range; exact-zero values (astronomically
                                   unlikely from a continuous draw, but checked
                                   explicitly) are nudged away from zero so d/4
                                   and abs(d-b) are never degenerate by construction
"""

import sys
import time

import numpy as np
import pyodbc

sys.path.insert(0, ".")
from config import CONNECTION_STRING
from src.python.persistence import sample_data_ids

SEED = 42
N_ROWS = 1_000_000
BATCH_SIZE = 100_000


def generate(n: int, seed: int):
    rng = np.random.default_rng(seed)

    data_id = np.arange(1, n + 1, dtype=np.int64)
    a = rng.uniform(0.0, 10.0, n)
    b = rng.uniform(1e-4, 20.0, n)
    c = rng.uniform(-10.0, 10.0, n)
    d = rng.uniform(-10.0, 10.0, n)

    zero_mask = d == 0.0
    if zero_mask.any():
        d[zero_mask] = 1e-6

    return data_id, a, b, c, d


def print_split_report(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> None:
    n = len(a)
    a_gt_5 = np.count_nonzero(a > 5)
    b_lt_10 = np.count_nonzero(b < 10)
    a_eq_c = np.count_nonzero(a == c)
    b_positive = np.count_nonzero(b > 0)
    d_nonzero = np.count_nonzero(d != 0)

    print("Branch-split verification (target: roughly 50/50 for a>5 and b<10):")
    print(f"  a > 5     : {a_gt_5:,} / {n:,}  ({100 * a_gt_5 / n:.2f}%)")
    print(f"  b < 10    : {b_lt_10:,} / {n:,}  ({100 * b_lt_10 / n:.2f}%)")
    print(f"  a == c    : {a_eq_c:,} / {n:,}  (expected ~0 -- continuous floats)")
    print(f"  b > 0     : {b_positive:,} / {n:,}  (must be {n:,}, i.e. 100%)")
    print(f"  d != 0    : {d_nonzero:,} / {n:,}  (must be {n:,}, i.e. 100%)")

    assert b_positive == n, "b must be strictly positive for every row"
    assert d_nonzero == n, "d must never be exactly zero"


def clear_existing(conn: pyodbc.Connection) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM dbo.t_log")
    cur.execute("DELETE FROM dbo.t_results")
    cur.execute("DELETE FROM dbo.t_sample")
    cur.execute("DELETE FROM dbo.t_data")
    conn.commit()


def seed_sample_table(conn: pyodbc.Connection) -> None:
    """Populate t_sample with the deterministic 10,000-id sample (seeded
    RNG, see persistence.sample_data_ids) that every engine persists its
    row-level results for. Generated once here rather than re-derived per
    engine -- see sql/01_schema.sql comment on t_sample for why."""
    ids = sample_data_ids()
    cur = conn.cursor()
    cur.fast_executemany = True
    cur.executemany("INSERT INTO dbo.t_sample (data_id) VALUES (?)", [(int(i),) for i in ids.tolist()])
    conn.commit()
    print(f"Seeded t_sample with {len(ids):,} deterministic ids.")


def bulk_load(conn: pyodbc.Connection, data_id, a, b, c, d) -> float:
    cur = conn.cursor()
    cur.fast_executemany = True

    rows = list(zip(data_id.tolist(), a.tolist(), b.tolist(), c.tolist(), d.tolist()))
    sql = "INSERT INTO dbo.t_data (data_id, a, b, c, d) VALUES (?, ?, ?, ?, ?)"

    start = time.perf_counter()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        cur.executemany(sql, batch)
        conn.commit()
        print(f"  loaded {min(i + BATCH_SIZE, len(rows)):,} / {len(rows):,} rows", end="\r")
    print()
    return time.perf_counter() - start


def main() -> None:
    print(f"Generating {N_ROWS:,} rows (seed={SEED})...")
    data_id, a, b, c, d = generate(N_ROWS, SEED)
    print_split_report(a, b, c, d)

    conn = pyodbc.connect(CONNECTION_STRING)
    try:
        print("Clearing existing t_data / t_results / t_log...")
        clear_existing(conn)

        print(f"Bulk-loading {N_ROWS:,} rows in batches of {BATCH_SIZE:,}...")
        elapsed = bulk_load(conn, data_id, a, b, c, d)
        print(f"Load complete in {elapsed:.2f}s ({N_ROWS / elapsed:,.0f} rows/sec).")

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.t_data")
        count = cur.fetchone()[0]
        assert count == N_ROWS, f"expected {N_ROWS} rows in t_data, found {count}"
        print(f"Verified: t_data now has {count:,} rows.")

        seed_sample_table(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
