# PaymentSystem — Dynamic Formula Evaluation Benchmark

**Live report:** https://leah-katz.github.io/dynamic-formula-benchmark/

A payments system computes hundreds of payment types from formulas stored as
strings in a database and evaluated dynamically at runtime. This project
implements five different strategies for evaluating those formulas over a
1,000,000-row dataset, benchmarks them against each other, cross-verifies they
all produce identical results, and recommends the best one. See **REPORT.md**
for the full writeup and **SEMANTICS.md** for the cross-engine evaluation
contract every method must satisfy identically.

## Architecture

```
                          t_targil (formula catalog, 13 formulas)
                                     |
                          t_data (1,000,000 rows: a, b, c, d)
                                     |
        +---------------+---------------+---------------+---------------+
        |               |               |               |               |
   python_eval    python_numpy      sql_sp         dotnet_datatable  dotnet_exprtree
   (eval() per    (vectorized       (T-SQL,        (naive baseline,  (compile once,
    row, x1)       NumPy arrays)     set-based,      DataColumn        Expr Trees,
                                     sp_executesql)   .Expression)      cached delegate)
        |               |               |               |               |
        +---------------+-------+-------+---------------+---------------+
                                 |
                     each engine independently:
                     - validates the formula (own parser, whitelist grammar)
                     - computes over all 1,000,000 rows
                     - persists a shared deterministic 10,000-row sample
                       to t_results, + full-dataset checksum to t_log
                                 |
                     scripts/compare_results.py
                     (row-level + full-dataset cross-verification,
                      tolerance 1e-9, exits non-zero on any mismatch)
                                 |
                     scripts/export_report.py
                     (writes report/public/assets/results.json)
                                 |
                     report/ -- Angular 22 dashboard
                     (charts, summary table, correctness badge,
                      winner callout -- all driven by real data)
```

Shared validation contract: every engine's own parser (`src/python/formula_parser.py`,
`src/dotnet/PaymentSystem.Shared/FormulaParser.cs`,
`sql/02_sp_calc_formula.sql`'s `sp_pf_*` procedures) independently implements the
grammar in `SEMANTICS.md` §2 — formulas come from a database table, i.e. from
outside each program's trust boundary, and are validated before ever reaching
`eval()` / a NumPy expression / a compiled delegate / `sp_executesql`.

## Prerequisites

- **Windows**, SQL Server 2025 Developer Edition (or 2022+; `LEAST`/`GREATEST`
  require 2022+), local instance, Windows Authentication
- **ODBC Driver 18 for SQL Server**
- **Python 3.11+** with `pyodbc`, `numpy` (`pip install -r requirements.txt`)
- **.NET SDK** — this project targets **net10.0**, not net8.0 as originally
  planned; only .NET 10 was available in the dev environment and retargeting
  was a disclosed, approved deviation (see git history / REPORT.md §5). If you
  have .NET 8 and want to match the original spec, retarget the three `.csproj`
  files in `src/dotnet/` back to `net8.0`.
- **Node.js 20+** / npm, for the Angular report app only

### Step 0 — environment check

```
sqlcmd -S localhost -E -C -Q "SELECT @@VERSION"
```

If that fails, install SQL Server 2025 Developer Edition (free) + SSMS, then the
ODBC Driver 18. Create the database once:

```sql
CREATE DATABASE PaymentSystem;
ALTER DATABASE PaymentSystem SET RECOVERY SIMPLE;
```

The connection string lives in exactly one place per language: `config.py`
(Python, ODBC syntax) and `src/dotnet/PaymentSystem.Shared/Config.cs` (C#,
ADO.NET syntax) — both read an env var first
(`PAYMENTSYSTEM_CONNECTION_STRING` / `PAYMENTSYSTEM_CONNECTION_STRING_DOTNET`)
and fall back to a local Windows-auth default.

## Running everything

One command reproduces every number in REPORT.md from a clean database:

```
pip install -r requirements.txt
python run_all.py
```

This runs, in order: schema → seed 1,000,000 rows + the shared 10,000-id
sample table → seed the 13-formula catalog → create the T-SQL stored
procedure → all 5 engines → `compare_results.py` (exits non-zero on any
mismatch) → `export_report.py` (writes `report/public/assets/results.json`).
Takes about 3.5 minutes on the reference machine.

To run pieces individually:

```
sqlcmd -S localhost -E -C -i sql/01_schema.sql
python scripts/seed_data.py
python scripts/seed_formulas.py
sqlcmd -S localhost -E -C -i sql/02_sp_calc_formula.sql

python -m src.python.eval_engine
python -m src.python.numpy_engine
python -m src.sql.run_sp
dotnet run --project src/dotnet/DataTableCompute -c Release
dotnet run --project src/dotnet/ExpressionTrees -c Release

python scripts/compare_results.py
python scripts/export_report.py
```

Any engine also accepts `--persist=full` to write all 1,000,000 rows instead
of the 10,000-row sample (proves the full pipeline works end to end; not part
of the standard benchmark run since 1M rows × 13 formulas × 5 engines would be
~65M rows of pure I/O measurement — see REPORT.md / SEMANTICS.md §7 for why).

## Running the report app locally

```
cd report
npm install
ng serve
```

Then open `http://localhost:4200`. The app loads `public/assets/results.json`
at startup — regenerate it with `python scripts/export_report.py` after any
new benchmark run, then refresh.

## Deployment

Deployed via [`angular-cli-ghpages`](https://github.com/angular-schule/angular-cli-ghpages)
(a devDependency of `report/`), chosen over a GitHub Actions workflow because it
pushes the built output straight to a `gh-pages` branch over git with one
command — no CI run to wait on or debug, and it works from any machine with
push access, not just from GitHub's own runners:

```
cd report
npx ng build --base-href /dynamic-formula-benchmark/
npx angular-cli-ghpages --dir=dist/report/browser --branch=gh-pages
```

This creates/updates the `gh-pages` branch with exactly the build output
(plus a `.nojekyll` file and a `404.html` SPA-redirect fallback that the tool
adds automatically) and pushes it. GitHub Pages then serves it directly — no
manual **Settings → Pages** change was needed for this repo (Pages was
already serving from `gh-pages` once the branch existed); if it ever isn't,
set **Settings → Pages → Build and deployment → Source: Deploy from a
branch**, **Branch: `gh-pages` / `(root)`**.

Verify the deployed link actually renders before treating a deploy as done —
a wrong `--base-href` 404s every asset on a cold load. (On Windows + Git Bash,
watch out for MSYS path conversion mangling a leading-slash argument like
`--base-href /dynamic-formula-benchmark/` into a Windows path — prefix the
command with `MSYS_NO_PATHCONV=1` if that happens.)

## Screenshots

See `screenshots/README.md` for the checklist of what to capture (SSMS tables,
the comparison script's console output, the deployed report).
