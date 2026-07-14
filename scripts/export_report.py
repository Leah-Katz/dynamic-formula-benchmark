"""
export_report.py -- queries t_log + t_results + the real compare_results.py
verdict and writes report/public/assets/results.json. The Angular app loads
this file at startup; there is no live backend, so the report hosts
statically. Never hand-edit results.json -- it is a build artifact.
"""

import datetime
import json
import sys

sys.path.insert(0, ".")
from scripts import compare_results as cmp
from src.python import persistence

OUTPUT_PATH = "report/public/assets/results.json"


def classify(formula: dict) -> str:
    """simple / complex / conditional, per SEMANTICS.md's own grouping of
    the catalog (assignment brief Step 3): conditional if tnai is set,
    else simple if it's bare arithmetic with no function calls or
    parens, else complex. Generalizes cleanly if the catalog grows."""
    if formula["tnai"] is not None:
        return "conditional"
    targil = formula["targil"]
    has_func = any(name in targil for name in ("sqrt", "log", "abs", "min", "max", "pow"))
    has_parens = "(" in targil
    return "complex" if (has_func or has_parens) else "simple"


def fetch_latest_runs(conn) -> list[dict]:
    """One row per (method, targil_id) -- the most recent run of each."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT method, targil_id, run_time, rows_processed, compile_ms, eval_ms, persist_ms,
               checksum, null_count, run_ts
        FROM dbo.t_log t
        WHERE run_ts = (
            SELECT MAX(t2.run_ts) FROM dbo.t_log t2
            WHERE t2.targil_id = t.targil_id AND t2.method = t.method
        )
        ORDER BY method, targil_id
        """
    )
    return [
        {
            "method": r.method,
            "targilId": r.targil_id,
            "runTimeMs": r.run_time,
            "rowsProcessed": r.rows_processed,
            "compileMs": r.compile_ms,
            "evalMs": r.eval_ms,
            "persistMs": r.persist_ms,
            "checksum": r.checksum,
            "nullCount": r.null_count,
            "runTs": r.run_ts.isoformat(),
        }
        for r in cur.fetchall()
    ]


def build_summaries(runs: list[dict], method_labels: dict[str, str], all_targil_ids: list[int]) -> list[dict]:
    by_method: dict[str, list[dict]] = {}
    for run in runs:
        by_method.setdefault(run["method"], []).append(run)

    total_formula_count = len(all_targil_ids)
    raw = []
    for method, method_runs in by_method.items():
        total_runtime = sum(r["runTimeMs"] for r in method_runs)
        total_rows = sum(r["rowsProcessed"] for r in method_runs)
        covered_ids = {r["targilId"] for r in method_runs}
        raw.append(
            {
                "method": method,
                "label": method_labels.get(method, method),
                "totalRuntimeMs": total_runtime,
                "totalRowsProcessed": total_rows,
                "rowsPerSec": (total_rows / total_runtime * 1000.0) if total_runtime > 0 else 0.0,
                "formulaCount": len(method_runs),
                "totalFormulaCount": total_formula_count,
                # Diffed from the actual data (t_log vs. the full catalog),
                # never hardcoded -- reflects whatever coverage gap a given
                # run actually has, for any method, not just DataTable.Compute.
                "missingFormulaIds": sorted(set(all_targil_ids) - covered_ids),
            }
        )

    slowest = max(r["totalRuntimeMs"] for r in raw) if raw else 0.0
    for r in raw:
        r["speedupVsSlowest"] = (slowest / r["totalRuntimeMs"]) if r["totalRuntimeMs"] > 0 else 0.0

    return sorted(raw, key=lambda r: r["totalRuntimeMs"])


def build_winner(summaries: list[dict]) -> dict:
    # Winner = fastest method that covers every formula in the catalog --
    # dotnet_datatable is excluded from contention even if fast on the
    # subset it supports, since it can't evaluate the full catalog at all
    # (see DataColumnExpressionEmitter.cs). This is a recommendation for
    # REAL use, not just "won this benchmark on paper."
    max_formulas = max(s["formulaCount"] for s in summaries)
    eligible = [s for s in summaries if s["formulaCount"] == max_formulas]
    winner = min(eligible, key=lambda s: s["totalRuntimeMs"])
    return {
        "method": winner["method"],
        # Bilingual because this is data-generated prose with real per-run
        # numbers, not static UI chrome -- the frontend can't translate a
        # sentence it never sees the English source of, so both versions
        # are produced here from the same numbers, not translated client-side.
        "justificationEn": (
            f"Fastest method that covers every formula in the catalog: {winner['totalRuntimeMs']:.0f} ms total, "
            f"{winner['rowsPerSec']:.0f} rows/sec, {winner['speedupVsSlowest']:.0f}x faster than the slowest method. "
            "Compiles each formula once into a cached delegate, avoiding both per-row re-parsing and a DB round trip "
            "per formula."
        ),
        "justificationHe": (
            f"השיטה המהירה ביותר שמכסה את כל הנוסחאות בקטלוג: {winner['totalRuntimeMs']:.0f} ms סה\"כ, "
            f"{winner['rowsPerSec']:.0f} שורות בשנייה, פי {winner['speedupVsSlowest']:.0f} מהיר יותר מהשיטה האיטית ביותר. "
            "מהדרת כל נוסחה פעם אחת לנציג (delegate) שמור במטמון, וכך נמנעת גם מפענוח חוזר של הנוסחה בכל שורה וגם "
            "מסבב תקשורת נוסף מול מסד הנתונים עבור כל נוסחה."
        ),
    }


def main() -> None:
    conn = persistence.connect()
    try:
        formulas_raw = persistence.fetch_formulas(conn)
        runs = fetch_latest_runs(conn)
        comparison = cmp.run_comparison(conn)
    finally:
        conn.close()

    method_labels = {
        "python_eval": "Python eval()",
        "python_numpy": "Python NumPy",
        "dotnet_datatable": "C# DataTable.Compute",
        "dotnet_exprtree": "C# ExpressionTrees",
        "sql_sp": "T-SQL sp_executesql",
    }

    formulas = [
        {
            "targilId": f["targil_id"],
            "targil": f["targil"],
            "tnai": f["tnai"],
            "targilFalse": f["targil_false"],
            "category": classify(f),
        }
        for f in formulas_raw
    ]

    summaries = build_summaries(runs, method_labels, [f["targil_id"] for f in formulas_raw])
    winner = build_winner(summaries)

    verdict = {
        "allPass": comparison.all_pass,
        "tolerance": comparison.tolerance,
        "sampleSize": comparison.sample_size,
        "rowLevelPass": comparison.row_level_pass,
        "rowLevelFail": comparison.row_level_fail,
        "rowLevelNa": comparison.row_level_na,
        "fullDatasetPass": comparison.full_dataset_pass,
        "fullDatasetFail": comparison.full_dataset_fail,
        "fullDatasetNa": comparison.full_dataset_na,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    data = {
        "formulas": formulas,
        "runs": runs,
        "summaries": summaries,
        "verdict": verdict,
        "winner": winner,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {OUTPUT_PATH}")
    print(f"  {len(formulas)} formulas, {len(runs)} run rows, {len(summaries)} method summaries")
    print(f"  verdict: allPass={verdict['allPass']}")


if __name__ == "__main__":
    main()
