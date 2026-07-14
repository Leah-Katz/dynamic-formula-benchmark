"""
persistence.py -- shared data access + persistence strategy for the two
Python engines (eval_engine.py, numpy_engine.py).

Persistence strategy (SEMANTICS.md / brief Step 6): compute over all
1,000,000 rows always, but only ever *persist* a deterministic 10,000-row
sample to t_results -- the same data_ids for every engine and every formula,
so results are directly comparable row-by-row. The full-dataset checksum +
null_count (SEMANTICS.md section 7) is what actually verifies all 1M rows
without paying to write 1M rows x 13 formulas x 5 engines (~65M rows) to disk.
--persist=full is an escape hatch to prove a single engine can write the
full dataset end to end; it is not part of the standard benchmark run.
"""

import sys
import time

import numpy as np
import pyodbc

sys.path.insert(0, ".")
from config import CONNECTION_STRING

SAMPLE_SIZE = 10_000
SAMPLE_SEED = 123
TOTAL_ROWS = 1_000_000


def sample_data_ids() -> np.ndarray:
    """Generates the deterministic 10,000-id sample. Called exactly once, by
    scripts/seed_data.py, to populate dbo.t_sample. Every engine (Python,
    C#, T-SQL) reads the sample from that shared table via fetch_sample_ids()
    rather than calling this directly -- replicating one RNG algorithm
    bit-for-bit across three language runtimes would be fragile, and a
    shared table trivially guarantees every method persists the same ids."""
    rng = np.random.default_rng(SAMPLE_SEED)
    ids = rng.choice(np.arange(1, TOTAL_ROWS + 1), size=SAMPLE_SIZE, replace=False)
    ids.sort()
    return ids


def fetch_sample_ids(conn: pyodbc.Connection) -> np.ndarray:
    """The shared 10,000-id sample every engine persists results for. See
    dbo.t_sample (sql/01_schema.sql) and sample_data_ids() above."""
    cur = conn.cursor()
    cur.execute("SELECT data_id FROM dbo.t_sample ORDER BY data_id")
    return np.array([r[0] for r in cur.fetchall()], dtype=np.int64)


def connect() -> pyodbc.Connection:
    return pyodbc.connect(CONNECTION_STRING)


def fetch_formulas(conn: pyodbc.Connection) -> list[dict]:
    cur = conn.cursor()
    cur.execute("SELECT targil_id, targil, tnai, targil_false FROM dbo.t_targil ORDER BY targil_id")
    return [
        {"targil_id": r.targil_id, "targil": r.targil, "tnai": r.tnai, "targil_false": r.targil_false}
        for r in cur.fetchall()
    ]


def fetch_all_data(conn: pyodbc.Connection):
    """Returns (data_id, a, b, c, d) as parallel numpy float64/int64 arrays,
    ordered by data_id. Loaded once per engine run, outside any per-formula
    compile/eval/persist timing -- it's a fixed setup cost shared by every
    formula, not part of what's being benchmarked."""
    cur = conn.cursor()
    cur.execute("SELECT data_id, a, b, c, d FROM dbo.t_data ORDER BY data_id")
    rows = cur.fetchall()
    data_id = np.empty(len(rows), dtype=np.int64)
    a = np.empty(len(rows), dtype=np.float64)
    b = np.empty(len(rows), dtype=np.float64)
    c = np.empty(len(rows), dtype=np.float64)
    d = np.empty(len(rows), dtype=np.float64)
    for i, r in enumerate(rows):
        data_id[i] = r.data_id
        a[i] = r.a
        b[i] = r.b
        c[i] = r.c
        d[i] = r.d
    return data_id, a, b, c, d


def write_log(
    conn: pyodbc.Connection,
    *,
    targil_id: int,
    method: str,
    run_time: float,
    rows_processed: int,
    compile_ms: float,
    eval_ms: float,
    persist_ms: float,
    checksum: float | None,
    null_count: int,
) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO dbo.t_log
            (targil_id, method, run_time, rows_processed, compile_ms, eval_ms, persist_ms, checksum, null_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        targil_id, method, run_time, rows_processed, compile_ms, eval_ms, persist_ms, checksum, null_count,
    )
    conn.commit()


def write_results_sample(
    conn: pyodbc.Connection,
    *,
    targil_id: int,
    method: str,
    sample_ids: np.ndarray,
    results_by_id: dict,
) -> float:
    """Writes the deterministic 10,000-row sample for this (targil_id, method).
    Returns elapsed persist time in ms."""
    cur = conn.cursor()
    cur.fast_executemany = True
    rows = [
        (int(did), targil_id, method, results_by_id.get(int(did)))
        for did in sample_ids.tolist()
    ]
    start = time.perf_counter()
    cur.executemany(
        "INSERT INTO dbo.t_results (data_id, targil_id, method, result) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return (time.perf_counter() - start) * 1000.0


def write_results_full(
    conn: pyodbc.Connection,
    *,
    targil_id: int,
    method: str,
    data_id: np.ndarray,
    results: np.ndarray,
) -> float:
    """--persist=full: writes all 1,000,000 rows for one (targil_id, method)
    via fast_executemany, batched. Returns elapsed persist time in ms."""
    cur = conn.cursor()
    cur.fast_executemany = True
    values = [None if (v is None or np.isnan(v)) else float(v) for v in results.tolist()]
    rows = list(zip(data_id.tolist(), [targil_id] * len(data_id), [method] * len(data_id), values))

    batch_size = 100_000
    start = time.perf_counter()
    for i in range(0, len(rows), batch_size):
        cur.executemany(
            "INSERT INTO dbo.t_results (data_id, targil_id, method, result) VALUES (?, ?, ?, ?)",
            rows[i : i + batch_size],
        )
        conn.commit()
    return (time.perf_counter() - start) * 1000.0
