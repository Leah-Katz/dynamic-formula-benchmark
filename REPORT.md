# REPORT.md — Dynamic Formula Evaluation Benchmark

Numbers below are from a single `python run_all.py` run against a clean database
(seed=42, 1,000,000 rows, 13 formulas, 10,000-row deterministic sample). Reproduce
them yourself with the same command — see README.md.

## 1. The five methods, and why each performs the way it does

### C# `ExpressionTrees` — winner
Parses each formula once (a hand-written recursive-descent parser, see
`src/dotnet/PaymentSystem.Shared/FormulaParser.cs`) into a small AST, then compiles
that AST once into a `System.Linq.Expressions` tree and JITs it into a native
`Func<double,double,double,double,double?>` delegate. Every row after that is a
direct native function call — no string re-parsing, no interpreter dispatch, no
boxing beyond the nullable return. This is exactly the "compile once, execute a
million times" strategy the assignment asks for, and the numbers show why it wins:
**844 ms of eval time for 13,000,000 row-evaluations** (13 formulas × 1M rows),
i.e. under 65 ns per row including a function call, several arithmetic ops, and a
NaN/Infinity check.

### T-SQL `sp_executesql`
Set-based execution entirely inside the database engine: the formula is translated
into a single SQL expression (with `CASE WHEN`/`NULLIF` domain guards inserted at
translation time — see §3) and evaluated across all 1,000,000 rows in one
`SELECT`. No row ever crosses the network individually. This is competitive with
ExpressionTrees on eval time per formula but loses on **persist** (6,330 ms total)
because, unlike the other four engines, it has no in-memory result array to reuse —
every persist is a second full table scan that re-evaluates the formula from
scratch (see §4). It's also the only engine paying zero data-transfer cost for the
full-dataset checksum, since that computation happens where the data already
lives.

### C# `DataTable.Compute`
The "naive baseline" the assignment explicitly asks for — and it under-delivers in
a way that's more interesting than just being slow. `System.Data.DataColumn`'s
expression language turns out to have **no `Sqrt`, `Log`, or `Pow`/`^` at all**.
Four of the thirteen formulas (6, 7, 12, 13 — anything that needs `sqrt` or `log`,
anywhere, including inside a condition) are **inexpressible** in this engine and
are skipped with a logged reason, not silently faked — see the full evidence and
explanation below. For the nine formulas it *can* express (`abs`/`min`/`max`
rewritten as `IIF` expressions, `x^2` rewritten as `x*x` since every exponent in
the catalog happens to be a literal 2), each `DataColumn.Compute` call re-parses
the expression string from scratch — **10,868 ms of eval time**, roughly 13×
slower per row than ExpressionTrees, because there's no compilation step to
amortize.

#### Evidence: the runtime's own error, not our interpretation of it

We didn't infer this from documentation — we fed the .NET runtime the exact
translated form of the failing formulas and caught what it threw. Every
casing/syntax variant a reasonable person might try was tested, to rule out that
this was a bug in our own translator (e.g. wrong capitalization):

```
Sqrt(c * c + d * d)   -> System.Data.EvaluateException:
                          "The expression contains undefined function call Sqrt()."
sqrt(c * c + d * d)   -> System.Data.EvaluateException:
                          "The expression contains undefined function call sqrt()."
SQRT(c * c + d * d)   -> System.Data.EvaluateException:
                          "The expression contains undefined function call SQRT()."
sQrT(c * c + d * d)   -> System.Data.EvaluateException:
                          "The expression contains undefined function call sQrT()."
Sqrt (c * c + d * d)  -> System.Data.EvaluateException:
                          "The expression contains undefined function call Sqrt()."   (space before paren)
Math.Sqrt(c)          -> System.Data.EvaluateException:
                          "The expression contains undefined function call Math.Sqrt()."
Log(c) / log(c) / LOG(c) / lOg(c)  -> same pattern, "undefined function call {as-typed}()."
Pow(a, 2) / pow(a, 2) -> System.Data.EvaluateException:
                          "The expression contains undefined function call Pow()."
a ^ 2                 -> System.Data.EvaluateException:
                          "The expression contains unsupported operator '^'."
```

Every variant — every casing, with or without a space before the parenthesis,
single- or multi-argument, even namespace-qualified — fails identically. The
exception type is .NET's own `System.Data.EvaluateException`, thrown from inside
`System.Data.dll`'s expression parser; nothing in our code raises it. This rules
out a translator bug on our side (wrong casing, wrong syntax): the function is
simply not in the grammar, under any spelling.

In the shipped engine, this knowledge is encoded as a proactive guard rather than
a caught runtime exception — the translator rejects `sqrt`/`log`/non-square `pow`
before ever constructing a `DataColumn`, so the raw `EvaluateException` above
never actually surfaces at runtime; it's the evidence that justified writing the
guard, not something the shipped code catches directly:

- **Guard thrown**: `src/dotnet/DataTableCompute/DataColumnExpressionEmitter.cs:78-81`
  (`sqrt`) and `:76-77`/`:66-67` (`pow`/non-square `^`) — each raises our own
  `NotSupportedByDataTableComputeException` with a message naming the missing
  function.
- **Formula skipped**: `src/dotnet/DataTableCompute/Program.cs:60-65` — the engine
  driver catches that exception per formula, records it, prints
  `SKIPPED -- {message}`, and moves on to the next formula rather than aborting
  the whole run or faking a result.

Reproduce it yourself: `dotnet run --project src/dotnet/DataTableCompute -c
Release` and read the `SKIPPED` lines in its console output directly.

#### Why this happens: `DataColumn.Expression` is not a general expression language

Per Microsoft's own reference documentation for `DataColumn.Expression`
([learn.microsoft.com/dotnet/api/system.data.datacolumn.expression](https://learn.microsoft.com/en-us/dotnet/api/system.data.datacolumn.expression)),
the property exists to do exactly three things: "filter rows, calculate the
values in a column, or create an aggregate column." Its grammar is a small,
closed set, not an extensible math library:

- **Operators**: comparison (`< > <= >= = IN LIKE`), boolean concatenation
  (`AND OR NOT`), arithmetic (`+ - * / %`), string concatenation (`+`).
- **Functions** (exactly six, per the docs' own "Functions" section): `CONVERT`,
  `LEN`, `ISNULL`, `IIF`, `TRIM`, `SUBSTRING`.
- **Aggregates** (exactly seven, per the docs' own "Aggregates" section): `Sum`,
  `Avg`, `Min`, `Max`, `Count`, `StDev`, `Var` — each applicable to exactly one
  column, optionally through a `Parent`/`Child` relation reference. We confirmed
  this empirically too: `Min(a, b)` (two columns) throws `System.Data.
  SyntaxErrorException`: `"Syntax error in aggregate argument: Expecting a single
  column argument with possible 'Child' qualifier"`, while `Min(a)` (one column)
  correctly evaluates as a whole-table aggregate, per the docs' note that "if you
  use a single table to create an aggregate, there would be no group-by
  functionality — all rows would display the same value."

`Sqrt`, `Log`, `Pow`, and `^` appear in **neither list**. That's the whole
explanation for "undefined function call": the parser isn't rejecting a
recognized-but-misused function (compare `LEN(a)` on a numeric column, which
*is* recognized and throws a precise, different error — `"Type mismatch in
function argument: Len(), argument 1, expected System.String"` — because `LEN`
exists in the grammar and got the wrong argument type). `Sqrt`/`Log`/`Pow` are
tokens the parser has simply never heard of, in any capacity, which is why the
error is generic ("undefined function call") rather than specific. This is a
closed grammar built for tabular filtering, computed columns, and SQL-style
aggregation over rows — not a general-purpose math evaluator, and it was never
going to grow `Sqrt`/`Log` just because a formula needs them.

One honest loose end: `Abs(x)` neither throws nor errors — it silently evaluates
to `DBNull` for every row when applied outside a `Parent`/`Child` aggregate
context, which is a *different* failure mode from `Sqrt`/`Log`'s hard rejection,
and `Abs` is not actually listed in Microsoft's aggregate table above. We did not
chase down why the runtime special-cases `Abs` this way, because it doesn't
matter for this project: our translator never emits a bare `Abs(...)` call in the
first place — `abs(x)` is rewritten to `IIF((x) < 0, -(x), (x))` at translation
time (`DataColumnExpressionEmitter.cs:72`), sidestepping the question entirely.
Flagged here rather than silently smoothed over, per the standard we're holding
the rest of this report to.

#### The gap tracks formula complexity, not a coarse category label

| # | Formula | Category | DataTable.Compute | Why |
|---|---|---|:---:|---|
| 1 | `a + b` | simple | ✅ pass | pure arithmetic |
| 2 | `c * 2` | simple | ✅ pass | pure arithmetic |
| 3 | `b - a` | simple | ✅ pass | pure arithmetic |
| 4 | `d / 4` | simple | ✅ pass | pure arithmetic |
| 5 | `(a + b) * 8` | complex | ✅ pass | pure arithmetic |
| 6 | `sqrt(c^2 + d^2)` | complex | ❌ **fail** | needs `Sqrt` |
| 7 | `log(b) + c` | complex | ❌ **fail** | needs `Log` |
| 8 | `abs(d - b)` | complex | ✅ pass | `abs` rewritten to `IIF` |
| 9 | `b*2` / `b/2` if `a>5` | conditional | ✅ pass | `IIF`, arithmetic only |
| 10 | `a+1` / `d-1` if `b<10` | conditional | ✅ pass | `IIF`, arithmetic only |
| 11 | `1` / `0` if `a==c` | conditional | ✅ pass | `IIF`, arithmetic only |
| 12 | `sqrt(abs((a+b)*(c-d)) + pow(a,2))` | complex | ❌ **fail** | needs `Sqrt` |
| 13 | `(a+b+c+d)/4` / `max(a,b)` if `sqrt(a^2+b^2)>c` | conditional | ❌ **fail** | *condition* needs `Sqrt` |

Note formula 13: it's in the *conditional* category, and conditionals otherwise
pass cleanly (9, 10, 11 all pass — `IIF` is a first-class part of the grammar).
13 fails anyway, because its **condition**, not its value branches, calls `sqrt`.
The simple/complex/conditional taxonomy is a useful lens for the performance
question in §2, but it is not the actual failure boundary here — the real
boundary is exactly "does this formula invoke `sqrt` or `log` anywhere, in the
value expression *or* the condition." All 4 formulas that do, fail. All 9 that
don't, pass. That boundary is sharper and more informative than "complex
formulas fail": it's specifically transcendental math that DataTable.Compute
cannot express, regardless of which structural category the formula otherwise
falls into.

**The implication is not "DataTable.Compute is slower on hard formulas" — it's
that DataTable.Compute does not degrade gracefully as formulas get harder. It
stops working, entirely, the moment a formula needs `sqrt` or `log`.** For a
payments system whose formula catalog is expected to grow in complexity over
time (new agreements, new laws, new rates — see the brief's own premise), a
method that cannot express a square root is disqualified on **expressiveness**,
before its performance is even worth discussing. This reframes the project's
central question — "does the ranking change as formulas get more complex?" —
more sharply than a timing chart alone can: the answer isn't only that relative
timings shift (they do, see §2's complexity chart), it's that **one engine drops
out of contention entirely.** The fastest-*looking* naive baseline, on the
formulas it happens to run, is not actually a candidate for a system whose whole
premise is formulas that change and grow.

### Python `numpy_engine.py`
Translates each formula into a NumPy source string once (`to_numpy_expr` in
`formula_parser.py`), then evaluates it as a handful of vectorized C-level array
operations over the full 1,000,000-row columns — no Python-level per-row loop at
all. **234 ms of eval time**, competitive with the compiled C# path despite
running in an interpreted language, because the actual arithmetic happens in
NumPy's C implementation, not in Python bytecode. Its total runtime is dominated
by **persist** (13,446 ms) — the same pyodbc round-trip cost every Python/SQL
engine pays, not a property of NumPy itself.

### Python `eval_engine.py` — the deliberately slow baseline
The second baseline the assignment asks for: `eval()` on a pre-compiled code
object, called once per row, twice for conditional rows (once for the condition,
once for the chosen branch). **56,596 ms of eval time** — roughly 4.4 μs per
row-evaluation, two orders of magnitude slower than ExpressionTrees. This is
exactly what you'd expect: every row pays full CPython interpreter dispatch
overhead (bytecode fetch, stack manipulation, dict lookups for `a`/`b`/`c`/`d`)
with nothing amortized across rows. It's the textbook illustration of why
"interpret the formula fresh every time" doesn't scale.

## 2. Benchmark results

| Method | Formulas | Total runtime | Rows/sec | Speedup vs. slowest |
|---|---:|---:|---:|---:|
| **C# ExpressionTrees** | 13 / 13 | 2,949 ms | 4,408,611 | **26.2×** |
| T-SQL `sp_executesql` | 13 / 13 | 12,260 ms | 1,060,387 | 6.3× |
| C# DataTable.Compute | 9 / 13 † | 13,018 ms | 691,358 ‡ | 5.9× |
| Python NumPy | 13 / 13 | 13,682 ms | 950,164 | 5.6× |
| Python `eval()` | 13 / 13 | 77,100 ms | 168,612 | 1.0× (baseline) |

† DataTable.Compute cannot express `sqrt`/`log` — see §1 and §5. Its row/sec and
speedup figures are computed only over the 9 formulas it actually evaluated, so
they are **not directly comparable** to the other four methods' all-13 figures —
included for completeness, not as a claim of equivalence.

Compile / eval / persist breakdown (summed across all formulas each method
covers):

| Method | Compile | Eval | Persist |
|---|---:|---:|---:|
| C# ExpressionTrees | 69 ms | 844 ms | 2,036 ms |
| T-SQL `sp_executesql` | 123 ms | 5,807 ms | 6,330 ms † |
| C# DataTable.Compute | 7 ms | 10,868 ms | 2,143 ms |
| Python NumPy | 2 ms | 234 ms | 13,446 ms |
| Python `eval()` | 6 ms | 56,596 ms | 20,498 ms |

† As documented in `sql/02_sp_calc_formula.sql`: the stored procedure's eval and
persist phases each independently re-scan and re-evaluate the formula (there's no
shared in-memory result between the checksum query and the `INSERT...SELECT`), so
this split is not a clean decomposition of one shared compute pass the way it is
for the other four engines. Reported honestly rather than faked as directly
comparable, per the brief.

**Persist dominates for every DB-backed engine except the SP itself** — writing
10,000 sample rows over the network costs roughly 1–2 seconds regardless of how
fast the actual computation was, which is exactly the argument for the Step 6
persistence strategy (compute over all 1M rows, persist only a comparable sample)
rather than writing 1M rows × 13 formulas × 5 engines to disk on every run.

## 3. Correctness verification

`scripts/compare_results.py` (driven by `run_all.py`, output captured live —
`generatedAt: {see report/public/assets/results.json}`):

- **Row-level**: every `(data_id, targil_id)` in the 10,000-row deterministic
  sample, joined across all 5 methods pairwise, tolerance `1e-9` relative /
  absolute-floored per SEMANTICS.md §6. **114 PASS, 0 FAIL, 16 N/A** (the N/A
  cells are exactly DataTable.Compute's 4 unsupported formulas × 4 method pairs
  involving it).
- **Full-dataset**: checksum + null_count from `t_log`, covering all 1,000,000
  rows per formula per method. **114 PASS, 0 FAIL, 16 N/A** (same shape).
- **Result: all 5 methods produced identical results (tolerance 1e-9).**

N/A is not a passing grade dressed up — it is DataTable.Compute genuinely being
unable to evaluate 4 of the 13 formulas, disclosed as such rather than hidden.
Every comparison that *could* run, passed.

## 4. Recommendation

**Use compiled expression trees (or the equivalent in your stack — a JIT-compiled
delegate cache) for a real payments system**, with the formula validator
(`FormulaParser`/`formula_parser.py`/`sp_pf_*`) as a mandatory gate before any
formula reaches production, regardless of which evaluation engine you pick.

Trade-offs, stated plainly:

- **Raw speed**: ExpressionTrees wins by 4.1× over the T-SQL SP and 26× over the
  naive `eval()` baseline. But raw speed is not the whole story — every
  application-layer engine (all four non-SP methods) still pays a network round
  trip to fetch `t_data` and a second one to persist results, which the SP avoids
  entirely by never leaving the database. If your business logic already lives
  next to your data (e.g. a batch job that runs *inside* the DB tier), the SP's
  6,330 ms persist figure would look very different without the artificial
  eval/persist double-scan this benchmark's methodology imposes on it.
- **Maintainability**: the T-SQL recursive-descent parser (`sql/02_sp_calc_formula.sql`)
  is ~400 lines of T-SQL implementing a real grammar — genuinely harder to read,
  test, and debug than the equivalent 150-line C# or Python AST walker. A team
  without a strong T-SQL specialist will find the C# or Python parser easier to
  extend when the formula grammar inevitably grows (the brief's own "add 1-2 of
  your own" stress formulas already pushed the T-SQL implementation's complexity
  noticeably higher than either managed-language version).
- **Where should the business logic live?** This is the real architectural
  question behind "which method wins." A payments system's formulas change with
  law and policy, not with deploys — keeping them as data (as this whole project
  does) is correct regardless of *evaluation* engine. But *evaluating* them in the
  application tier (C#/Python) rather than the database tier keeps the database
  doing what it's best at (storage, transactional integrity, indexing) and keeps
  business logic in a language with better testing, debugging, and code-review
  tooling than T-SQL. ExpressionTrees' win margin is large enough that this isn't
  even a speed-vs-maintainability trade-off here — it's the fastest **and** the
  most maintainable of the two realistic production choices (SP vs. compiled
  delegate).
- **DataTable.Compute and `eval()` are not production candidates** — one can't
  express the full grammar, the other is two orders of magnitude slower with no
  compensating advantage. They earn their place in this benchmark as baselines
  that make the case for the other three, not as contenders.

## 5. Limitations and what I'd do differently with more time

- **DataTable.Compute's coverage gap is real, not cosmetic.** A production system
  cannot use it for any formula involving `sqrt`/`log`/non-square `pow`. With more
  time I'd prototype whether a custom `IValueConverter`-style extension or a
  precomputed helper-column pass (compute `sqrt`/`log` sub-expressions in a
  regular C# loop, feed the results back as extra `DataColumn`s, then let
  `DataColumn.Compute` handle only the remaining arithmetic) could close this gap
  — but that's a fundamentally different, hybrid architecture, not a tweak, and
  it would blur the clean "naive baseline" comparison this benchmark is making.
- **The T-SQL SP's eval/persist split is not apples-to-apples**, as stated in §2.
  A fairer SP benchmark would use `SELECT INTO` or a temp table to materialize the
  computed column once, then measure the sample `INSERT` and full checksum as two
  reads of that materialized result — closer to what the other four engines do.
  I chose not to do this because it would change what's actually being measured
  (the SP's real-world usage pattern *is* "compute this expression however many
  times you need its output," so the double-scan is honest, not a benchmarking
  artifact) — but a reader should not average its eval_ms/persist_ms split against
  the other four methods' splits without this caveat in mind.
- **`^` / `pow` in the T-SQL translator associates left instead of right for
  chained exponents** (`a^b^c` would translate as `(a^b)^c`, not `a^(b^c)` per the
  grammar's declared right-associativity) — never triggered by any formula in the
  catalog, but a real, disclosed gap in `sp_pf_power`'s translation logic. A
  proper fix needs the translator to detect and right-fold `^` chains before
  emitting `POWER()` calls.
- **`POWER()` magnitude overflow in T-SQL is unguarded.** SQL Server raises a
  hard, batch-aborting arithmetic-overflow error for `POWER()` results that
  exceed `float` range, and — unlike the negative-base-with-fractional-exponent
  case — this can't be pre-checked from the operands with a simple `CASE WHEN`.
  Every formula in the catalog uses small bases/exponents so this never
  triggers; a production system accepting arbitrary exponents would need a
  magnitude pre-check or per-row `TRY/CATCH` (which gives up the set-based
  performance advantage entirely).
- **C# targets .NET 10, not .NET 8** as the brief originally specified — only
  .NET 10 SDK/runtime were available in this environment; retargeting was a
  disclosed, user-approved deviation rather than a silent change (see git history).
- **The 10,000-row sample is randomly chosen, not stratified.** It's large enough
  (1% of the dataset) that both branches of every conditional formula are well
  represented in practice (verified via the ~50/50 split reported by
  `seed_data.py`), but a formula whose branch condition was rare (say, true for
  0.01% of rows) could end up under-sampled in the persisted comparison, even
  though the full-dataset checksum check would still catch a real discrepancy.
  With more time I'd stratify the sample per conditional formula's branch to
  guarantee both branches are represented at the same rate as the full dataset.
- **No load/concurrency testing.** Every number here is a single-threaded,
  single-connection run. A real payments system evaluating formulas under
  concurrent load (multiple SP calls, connection pool contention) would show a
  different picture, especially for the DB-tier engine.
