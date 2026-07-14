# Claude Code Prompt — Dynamic Formula Evaluation Benchmark (SQL Server + Angular)

Copy everything below the line into Claude Code.

---

You are helping me build a take-home assignment for a senior developer position at the Israeli Ministry of Education. I am a developer with 7 years of experience — write production-quality code, not tutorial code. Be opinionated, and tell me if you disagree with a decision.

I am on **Windows**, working in `cmd`. I do **not** have SQL Server installed yet — walk me through it (Step 0) before writing any code.

## Context

A payments system computes hundreds of payment types. The formulas change constantly (new agreements, new laws, new rates), so formulas are NOT hardcoded — they are stored as strings in a database table and evaluated dynamically at runtime.

The goal of this project is to **implement several different strategies for evaluating dynamic formulas over a large dataset, benchmark them against each other, verify they all produce identical results, and recommend the best one.**

## Tech stack (already decided — do not change without telling me why)

- **Database:** **Microsoft SQL Server 2025** (Developer Edition, local, Windows Authentication), database name `PaymentSystem`
- **Compute engines:** Python 3.11+ (`pyodbc`) and C# / .NET 8 (`Microsoft.Data.SqlClient`)
- **Report UI:** **Angular 17+** (standalone components, TypeScript strict mode), charts via Chart.js, deployed to **GitHub Pages**
- **Repo:** git, with a clean commit history

## Step 0 — Environment setup (do this with me before any code)

1. Check whether SQL Server is already installed and reachable (`sqlcmd -S localhost -E -Q "SELECT @@VERSION"`).
2. If not, give me the exact steps: download **SQL Server 2025 Developer Edition** (free), Basic install, then **SSMS** (SQL Server Management Studio) for the screenshots the assignment requires.
3. Verify I have the **ODBC Driver 18 for SQL Server** (needed by `pyodbc`). If not, tell me where to get it.
4. Once connected, create the `PaymentSystem` database and set its recovery model to **SIMPLE** — I'm about to bulk-insert a million rows and I don't want the transaction log to explode.
5. Put the connection string in **one** place (`config.py` / `appsettings.json`), read from an env var with a sane default (`Server=localhost;Database=PaymentSystem;Trusted_Connection=True;TrustServerCertificate=True`). No connection strings scattered across files.

Stop and confirm the connection works before moving on.

## Step 1 — Schema (`sql/01_schema.sql`, T-SQL)

Table and column names are dictated by the assignment — match them exactly:

```sql
t_data     (data_id INT PK, a FLOAT NOT NULL, b FLOAT NOT NULL, c FLOAT NOT NULL, d FLOAT NOT NULL)
t_targil   (targil_id INT PK, targil VARCHAR(500) NOT NULL, tnai VARCHAR(500) NULL, targil_false VARCHAR(500) NULL)
t_results  (results_id INT IDENTITY PK, data_id INT FK->t_data, targil_id INT FK->t_targil,
            method VARCHAR(50) NOT NULL, result FLOAT NULL)
t_log      (log_id INT IDENTITY PK, targil_id INT FK->t_targil, method VARCHAR(50) NOT NULL,
            run_time FLOAT NOT NULL)
```

Extend `t_log` with these extra columns — I want a fair benchmark, not a single meaningless number:
`rows_processed INT, compile_ms FLOAT, eval_ms FLOAT, persist_ms FLOAT, checksum FLOAT, run_ts DATETIME2`

**Semantics of `t_targil`:** if `tnai` is NULL, the row is a plain formula → evaluate `targil`.
If `tnai` is not NULL, the row is conditional → evaluate `targil` when the condition holds, otherwise evaluate `targil_false`.

Index `t_results` on `(targil_id, method, data_id)` — the comparison script will hammer it.

## Step 2 — Data generation (`scripts/seed_data.py`)

- Generate **1,000,000 rows** in `t_data` with a **fixed random seed** so the dataset is reproducible.
- Value ranges must make the formulas meaningful and mathematically valid:
  - `b` strictly positive (so `log(b)` is defined)
  - `d` never exactly zero (so `d / 4` and `abs(d - b)` behave)
  - `a` spanning both sides of 5, and `b` spanning both sides of 10, so the conditional formulas actually branch both ways (roughly 50/50 — verify and print the split).
- **Bulk load properly.** Do not insert a million rows one at a time. Use `pyodbc` with `fast_executemany = True` in batched transactions, or generate a CSV and use `BULK INSERT` / `bcp` — your call, but justify it and print the elapsed load time. This must take seconds, not minutes. If you're about to write a row-by-row insert loop, stop and reconsider.

## Step 3 — Formula catalog (`scripts/seed_formulas.py`)

Insert at least 12 formulas into `t_targil`:

- **Simple:** `a + b`, `c * 2`, `b - a`, `d / 4`
- **Complex:** `(a + b) * 8`, `sqrt(c^2 + d^2)`, `log(b) + c`, `abs(d - b)`
- **Conditional** (populate `tnai` + `targil` + `targil_false`):
  - `tnai = "a > 5"`, `targil = "b * 2"`, `targil_false = "b / 2"`
  - `tnai = "b < 10"`, `targil = "a + 1"`, `targil_false = "d - 1"`
  - `tnai = "a == c"`, `targil = "1"`, `targil_false = "0"`
- **Add 1–2 of your own** that stress the engines (e.g. a deeply nested expression, or one mixing a condition with a complex sub-expression).

Note: `^` in the formula strings means exponentiation. Each engine must translate it to its own syntax (`**` in Python, `Math.Pow` in C#, `POWER()` in T-SQL).

## Step 4 — Shared evaluation semantics (`SEMANTICS.md` — write this FIRST, before any engine)

All five engines must agree, so define the contract up front. This is the single most important file in the project:

- All arithmetic in IEEE-754 **double** precision.
- **Domain errors** — division by zero, `log` of a non-positive number, `sqrt` of a negative number — produce **NULL**. Not NaN, not infinity, not an exception. Every engine must be forced into this behavior:
  - Python: catch `ValueError` / `ZeroDivisionError` → `None`
  - NumPy: `np.errstate` + mask NaN/inf → `None`
  - C#: check for `double.IsNaN` / `IsInfinity` → `null`
  - T-SQL: guard with `CASE WHEN b > 0 THEN LOG(b) ELSE NULL END` and `NULLIF(denominator, 0)` — do **not** rely on `SET ARITHABORT` behavior, be explicit
- Cross-engine comparison uses **relative tolerance 1e-9**.
- Each engine reports a **checksum** per formula = sum of all non-NULL results (float64) + a count of NULLs. This is how I verify 1M rows without persisting 1M rows per engine.

## Step 5 — Five evaluation engines

Each engine is a standalone program. Each runs over **all formulas × all 1,000,000 rows**, writes timing to `t_log`, and writes results to `t_results` (see persistence note).

1. **`src/dotnet/DataTableCompute`** — C#, `DataTable.Compute` (the naive baseline the assignment explicitly suggests). Expect it to be slow — that's the point of including it.
2. **`src/dotnet/ExpressionTrees`** — C#, parse each formula **once** into a `System.Linq.Expressions` tree, compile it to a `Func<double,double,double,double,double?>` delegate, cache the delegate per formula, then run it over all rows. The "compile once, execute a million times" strategy.
3. **`src/python/eval_engine.py`** — Python, `eval()` per row (the second baseline the assignment suggests). **Never pass raw DB strings to `eval`** — see the security note.
4. **`src/python/numpy_engine.py`** — Python, translate each formula into a **vectorized NumPy expression** evaluated over the entire 1M-element column arrays at once. `np.where` for conditionals.
5. **`sql/02_sp_calc_formula.sql`** — a real **T-SQL stored procedure** that takes a `@targil_id`, reads the formula from `t_targil`, builds the calculation SQL at runtime, and executes it with **`sp_executesql`** — set-based, entirely inside the database engine. Use `CASE WHEN <tnai> THEN <targil> ELSE <targil_false> END` for conditionals. This is the method the assignment describes most explicitly, so make it the strongest implementation, not an afterthought. Driven from `src/sql/run_sp.py`, which calls the proc per formula and records timing.

### Security note (do this — it earns points and it's the right call)

Formula strings come from a database, i.e. from outside the program. Never hand them to `eval()` and never string-concatenate them into `sp_executesql` unchecked — that is textbook SQL injection, and "the formula came from our own table" is not a defense.

Build a **shared formula parser** that:
- tokenizes the formula,
- validates it against a **whitelist** of allowed identifiers (`a`, `b`, `c`, `d`), operators, and functions (`sqrt`, `log`, `abs`, `min`, `max`, `pow`),
- rejects everything else (attribute access, calls, imports, dunder names, semicolons, comments) — in Python, walk the `ast` node tree, not a regex,
- then emits the target-specific expression: Python source / NumPy source / T-SQL fragment / C# expression tree.

The `eval()` engine still calls `eval()` (so the benchmark stays honest), but only on a **validated** expression, with `__builtins__` emptied. The stored procedure validates the formula before it reaches `sp_executesql`. Call this out explicitly in the report — the naive versions of both approaches are genuinely exploitable, and noticing that is part of the deliverable.

## Step 6 — Persistence strategy (a real engineering decision — implement it deliberately)

Writing 1M rows × 12 formulas × 5 engines to `t_results` is ~60M rows. That turns the benchmark into a disk-I/O measurement instead of a formula-evaluation measurement.

Implement it this way, and document the reasoning in the report:
- **Compute** over all 1,000,000 rows, always.
- **Persist** to `t_results`: a deterministic sample — the same 10,000 `data_id`s for every engine and every formula, so results are directly comparable — **plus** the full-dataset checksum in `t_log`.
- Provide a `--persist=full` flag that writes all 1M rows for a single engine, to prove it works end to end. Use `SqlBulkCopy` (C#) / `fast_executemany` (Python). I'll screenshot that.
- Split the timing: `compile_ms` (parse/compile the formula), `eval_ms` (pure computation over 1M rows), `persist_ms` (DB write). `run_time` = total. DB writes must never pollute the evaluation timing.

For the stored procedure, note honestly in the report that its "eval" and "persist" phases are hard to separate cleanly — measure `INSERT ... SELECT` as one number and say so rather than faking a breakdown.

## Step 7 — Correctness verification (`scripts/compare_results.py`)

- Join `t_results` across all 5 methods for every `(data_id, targil_id)` in the persisted sample.
- Compare with relative tolerance 1e-9. NULL must match NULL.
- Independently compare the **full-dataset checksums** in `t_log` across all 5 engines.
- Print a pass/fail matrix per formula per method pair, and exit non-zero on any mismatch.
- Output a clean summary I can screenshot.

## Step 8 — Report screen (Angular)

Build an **Angular 17+ application** in `report/`. This is a graded deliverable — treat it as real front-end code, not a throwaway page.

**Data flow:** `scripts/export_report.py` queries `t_log` + `t_results` + the comparison verdict and writes `report/src/assets/results.json`. The Angular app loads that JSON — no live backend, so it hosts statically.

**Architecture (show that you know modern Angular):**
- Standalone components, `provideHttpClient()`, TypeScript **strict** mode.
- A typed `BenchmarkService` exposing the data as a **signal**. Proper interfaces (`BenchmarkRun`, `FormulaResult`, `ComparisonVerdict`) — no `any`, anywhere.
- Container/presentational split: `dashboard` → `summary-cards`, `runtime-chart`, `complexity-chart`, `breakdown-chart`, `results-table`, `correctness-badge`. Presentational components take `input()`s and use `OnPush` change detection.
- Chart.js wrapped in a small reusable chart component.

**The screen must show:**
- a grouped bar chart of run time per method, per formula
- a chart comparing **simple vs complex vs conditional** formulas — does the ranking between methods change as formulas get more complex? That's the most interesting question in the project, so make this chart prominent
- the **compile / eval / persist** breakdown as a stacked bar per method
- a sortable summary table: method, total runtime, rows/sec, speedup vs. the slowest method
- a **correctness badge** — "All 5 methods produced identical results (tolerance 1e-9)" — driven by real output from `compare_results.py`, never hardcoded
- a clear **winner callout** with a one-line justification

**Quality bar:** clean, modern, responsive layout. A **log-scale toggle** on the runtime chart — the spread between methods will be orders of magnitude and a linear axis will flatten the fast ones to zero. Labels in Hebrew or English, pick one, be consistent.

**Deployment:** GitHub Pages. Get `ng build --base-href /<repo-name>/` right, or the assets will 404 on a cold load and the link will look broken to whoever grades it. Verify the deployed link actually renders before you tell me it's done. Put the live link at the top of the README.

## Step 9 — Documentation

- **`README.md`** — what this is, an architecture diagram (ASCII is fine), prerequisites, exact run order end to end, and the live report link.
- **`REPORT.md`** — the graded summary report:
  - an explanation of each of the 5 methods and *why* it performs the way it does (interpretation overhead, per-row dispatch, JIT-compiled delegates, vectorization, set-based execution inside the DB engine)
  - the benchmark results table
  - the correctness verification result
  - **a clear recommendation** for which method a real payments system should use, with trade-offs stated: raw speed vs. maintainability vs. whether the business logic should live in the database or the application
  - an honest "limitations and what I'd do differently with more time" section
- **`SEMANTICS.md`** — the evaluation contract from Step 4.
- **`screenshots/`** — folder + a README checklist of which screenshots I need to take (SSMS showing `t_data` / `t_targil` / `t_results` / `t_log`, the comparison script output, the deployed report screen).

## Step 10 — Orchestration

- One `run_all.py` that runs: schema → seed data → seed formulas → create SP → all 5 engines → comparison → export `results.json`. A single command must reproduce every number in the report from a clean database.
- `requirements.txt`, `.csproj`, `report/package.json`. `.gitignore` excludes `node_modules/`, `bin/`, `obj/`.
- Since the DB can't be committed to git, include `sql/` scripts that rebuild it from scratch, and note in the README that the grader can reproduce the whole dataset with one command.

## How I want you to work

1. **Step 0 first.** Get SQL Server installed and connected. Nothing else matters until `SELECT @@VERSION` returns.
2. Then write `SEMANTICS.md` and the shared formula parser, and **show them to me before building any engine**. Everything downstream depends on that contract being right.
3. Build the engines one at a time, running each after you write it. Do not write all five and then debug.
4. Run the comparison script and show me its output before you start on Angular.
5. Build the Angular app last, against real exported data — never against mocks.
6. Ask me before any decision that changes the deliverables.
7. Comment the code — code clarity and comments are explicit grading criteria.
8. Commit after each working milestone, with meaningful messages.

Start with Step 0.
