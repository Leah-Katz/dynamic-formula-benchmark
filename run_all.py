"""
run_all.py -- reproduces every number in REPORT.md from a clean database
with a single command: schema -> seed data -> seed formulas -> create SP ->
all 5 engines -> correctness comparison -> export report/public/assets/results.json.

Usage: python run_all.py
Requires: SQL Server reachable (see README Step 0), .NET SDK, Node not
needed here (only for the Angular app itself).
"""

import subprocess
import sys
import time

SQLCMD_ARGS = ["sqlcmd", "-S", "localhost", "-E", "-C"]

STEPS: list[tuple[str, list[str]]] = [
    ("Schema (sql/01_schema.sql)", [*SQLCMD_ARGS, "-i", "sql/01_schema.sql"]),
    ("Seed data (1,000,000 rows + sample table)", [sys.executable, "scripts/seed_data.py"]),
    ("Seed formulas (13-formula catalog)", [sys.executable, "scripts/seed_formulas.py"]),
    ("Create stored procedure (sql/02_sp_calc_formula.sql)", [*SQLCMD_ARGS, "-i", "sql/02_sp_calc_formula.sql"]),
    ("Engine: python_eval", [sys.executable, "-m", "src.python.eval_engine"]),
    ("Engine: python_numpy", [sys.executable, "-m", "src.python.numpy_engine"]),
    ("Engine: sql_sp", [sys.executable, "-m", "src.sql.run_sp"]),
    ("Engine: dotnet_datatable", ["dotnet", "run", "--project", "src/dotnet/DataTableCompute", "-c", "Release"]),
    ("Engine: dotnet_exprtree", ["dotnet", "run", "--project", "src/dotnet/ExpressionTrees", "-c", "Release"]),
    ("Correctness comparison (scripts/compare_results.py)", [sys.executable, "scripts/compare_results.py"]),
    ("Export report data (scripts/export_report.py)", [sys.executable, "scripts/export_report.py"]),
]


def run_step(label: str, cmd: list[str]) -> float:
    print(f"\n{'=' * 100}\n{label}\n{'=' * 100}")
    start = time.perf_counter()
    result = subprocess.run(cmd)
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        print(f"\nFAILED: {label} (exit code {result.returncode}) after {elapsed:.1f}s")
        sys.exit(result.returncode)
    print(f"-- {label} done in {elapsed:.1f}s")
    return elapsed


def main() -> None:
    overall_start = time.perf_counter()
    for label, cmd in STEPS:
        run_step(label, cmd)

    total = time.perf_counter() - overall_start
    print(f"\n{'=' * 100}")
    print(f"run_all.py complete in {total:.1f}s. Every number in REPORT.md is reproducible from this run.")
    print("Next: cd report && ng serve  (or deploy per README).")
    print("=" * 100)


if __name__ == "__main__":
    main()
