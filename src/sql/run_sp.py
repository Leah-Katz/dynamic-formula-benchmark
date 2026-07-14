"""
run_sp.py -- driver for the T-SQL stored procedure engine
(sql/02_sp_calc_formula.sql). Calls dbo.sp_calc_formula once per formula and
records the timing/checksum it returns.

The SP does its own validation (a recursive-descent parser written in
T-SQL, see sql/02_sp_calc_formula.sql) and writes directly to t_log /
t_results -- this script is a thin driver, not a second persistence layer.

Usage: python -m src.sql.run_sp [--persist=full]
"""

import argparse
import sys
import time

sys.path.insert(0, ".")
from src.python import persistence

METHOD = "sql_sp"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persist", choices=["sample", "full"], default="sample")
    args = parser.parse_args()
    persist_full = 1 if args.persist == "full" else 0

    conn = persistence.connect()
    try:
        formulas = persistence.fetch_formulas(conn)
        print(f"[{METHOD}] evaluating {len(formulas)} formulas (persist={args.persist})")

        start = time.perf_counter()
        for formula in formulas:
            cur = conn.cursor()
            cur.execute(
                "EXEC dbo.sp_calc_formula @targil_id=?, @method=?, @persist_full=?",
                formula["targil_id"], METHOD, persist_full,
            )
            row = cur.fetchone()
            conn.commit()
            print(
                f"  targil {row.targil_id:>2}: compile={row.compile_ms:8.2f}ms  eval={row.eval_ms:9.2f}ms  "
                f"persist={row.persist_ms:8.2f}ms  nulls={row.null_count:>7}  checksum={row.checksum:.6f}"
            )
        total = time.perf_counter() - start
        print(f"[{METHOD}] done in {total:.2f}s")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
