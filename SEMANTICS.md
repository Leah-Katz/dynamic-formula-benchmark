# SEMANTICS.md — Formula Evaluation Contract

This is the single contract all five engines (`DataTableCompute`, `ExpressionTrees`,
`eval_engine.py`, `numpy_engine.py`, the T-SQL stored procedure) must satisfy
identically. If an engine's output differs from this document, the engine is wrong,
not the document. Everything downstream — the shared parser, all five engines,
`compare_results.py` — is built against this file.

## 1. Data types

- All arithmetic is IEEE-754 **binary64 (`double`)**. No `decimal`, no `float32`.
- Inputs `a, b, c, d` are the four `FLOAT` columns of `t_data`, always non-NULL.
- A formula result is either a `double` or **NULL**. There is no third state.

## 2. Grammar (the whitelist)

A formula string is one of two things:

- **Plain formula** (`t_targil.tnai IS NULL`): a single arithmetic **value expression**.
  Evaluate `targil`.
- **Conditional formula** (`t_targil.tnai IS NOT NULL`): evaluate the **condition
  expression** `tnai`. If true, evaluate `targil`; if false, evaluate `targil_false`.

### 2.1 Value expression grammar

```
expr        := term (('+' | '-') term)*
term        := unary (('*' | '/') unary)*
unary       := '-' unary | power
power       := atom ('^' unary)?          -- right-associative, '^' = exponentiation
atom        := NUMBER
             | IDENTIFIER
             | FUNC1 '(' expr ')'
             | FUNC2 '(' expr ',' expr ')'
             | '(' expr ')'

IDENTIFIER  := 'a' | 'b' | 'c' | 'd'
FUNC1       := 'sqrt' | 'log' | 'abs'
FUNC2       := 'min' | 'max' | 'pow'
NUMBER      := standard decimal literal, e.g. 1, 5, 3.14, 0.5
```

### 2.2 Condition expression grammar (`tnai` only)

```
condition   := expr ('>' | '<' | '>=' | '<=' | '==' | '!=') expr
```

**Deliberate restriction:** a condition is exactly one comparison between two value
expressions. There is no `AND` / `OR` / `NOT` composition. Every formula in the
catalog fits this shape (including the "stress" formulas — a complex sub-expression
on either side of a comparison is allowed, e.g. `sqrt(a^2+b^2) > c`, just not
multiple chained comparisons). If a future formula genuinely needs boolean
composition, that's a grammar change to make explicitly, not something to bolt on
silently in one engine.

### 2.3 Explicitly rejected

The parser walks a real syntax tree (Python: `ast`, not regex) and rejects anything
outside the grammar above, including but not limited to:

- Any identifier other than `a`, `b`, `c`, `d` (no attribute access, no dunder names,
  no `__builtins__`, no arbitrary variable names)
- Any function name other than `sqrt`, `log`, `abs`, `min`, `max`, `pow`
- Assignment (`=`), semicolons, comments (`#`, `--`, `/* */`)
- String literals, boolean literals, `and`/`or`/`not`, `import`, list/dict/set
  literals, subscripting, slicing
- Anything that would require a second AST walk to catch — if it's not in the
  grammar above, it's rejected, full stop.

This whitelist is the security boundary described in Step 5 and applies identically
whether the target is Python `eval()`, a NumPy expression, a C# expression tree, or
a `sp_executesql` fragment. "The formula came from our own table" is not a reason to
skip validation — the table is still outside the program's trust boundary.

## 3. Function semantics

| Formula syntax | Meaning | Python | NumPy | C# | T-SQL |
|---|---|---|---|---|---|
| `sqrt(x)` | square root | `math.sqrt` | `np.sqrt` | `Math.Sqrt` | `SQRT()` |
| `log(x)` | **natural log (ln)** | `math.log` | `np.log` | `Math.Log` | `LOG()` (1-arg = natural log) |
| `abs(x)` | absolute value | `abs()` | `np.abs` | `Math.Abs` | `ABS()` |
| `min(x,y)` | minimum | `min()` | `np.minimum` | `Math.Min` | `LEAST()` (SQL Server 2022+) |
| `max(x,y)` | maximum | `max()` | `np.maximum` | `Math.Max` | `GREATEST()` (SQL Server 2022+) |
| `pow(x,y)` / `x^y` | exponentiation | `x ** y` | `np.power` | `Math.Pow` | `POWER()` |

`log` is explicitly natural log (ln), not log10 — this is the default meaning of
"log" in every one of these five runtimes' own `log()`/`LOG()` function, so it's the
only choice that doesn't require a special case anywhere.

`^` in a formula string is exponentiation, never XOR or bitwise anything. Every
engine must translate it to its own power operator/function per the table above.

## 4. Domain errors → NULL (the core rule)

**Any value expression whose evaluation would be undefined, or whose final result is
not a finite real number, produces NULL — never NaN, never ±Infinity, never a thrown
exception that escapes the row.**

Concretely:

- Division `x / y`: if `y == 0`, result is NULL (this includes `0 / 0`).
- `sqrt(x)`: if `x < 0`, result is NULL.
- `log(x)`: if `x <= 0`, result is NULL.
- `pow(x, y)` / `x ^ y`: if the mathematical result is not a finite real (e.g.
  negative base with a fractional exponent, or overflow to Infinity), result is
  NULL. Engines are **not** expected to special-case this — it falls out of rule
  below.
- **Catch-all:** after evaluating the full expression for a row, if the result is
  `NaN` or `±Infinity`, the result is NULL. This is what makes `pow`/`^` edge cases
  safe without enumerating every case: IEEE-754 already produces NaN/Inf for these,
  the engines just need to check for it once at the end rather than trying to
  pre-validate every sub-operation.

Per-engine mechanics (as decided in the original brief):

- **Python (`eval_engine.py`):** catch `ValueError` / `ZeroDivisionError` → `None`;
  also check `math.isnan/isinf` on the result in case an operation returns a float
  NaN/Inf without raising (rare with `math.*`, but be defensive).
- **NumPy (`numpy_engine.py`):** wrap in `np.errstate(all='ignore')` so warnings
  don't spam the console, then mask `np.isnan(result) | np.isinf(result)` and set
  those positions to `None`/NaN-sentinel before persistence (the underlying array
  stays `float64`; NULL is represented as `np.nan` in-memory and translated to SQL
  `NULL` at write time).
- **C# (both `DataTableCompute` and `ExpressionTrees`):** after computing a
  `double`, check `double.IsNaN(x) || double.IsInfinity(x)` → `(double?)null`.
- **T-SQL (stored procedure):** never rely on `SET ARITHABORT` / default error
  behavior. Be explicit: `NULLIF(denominator, 0)` for division, and
  `CASE WHEN b > 0 THEN LOG(b) ELSE NULL END` / `CASE WHEN x >= 0 THEN SQRT(x) ELSE NULL END`
  style guards for every domain-sensitive function. SQL Server will itself throw a
  runtime error for `LOG` of a non-positive number or return NULL for
  divide-by-zero depending on settings — we don't depend on that; the guard makes
  it NULL unconditionally, deterministically, before the engine ever gets a chance
  to error.

## 5. Condition evaluation (`tnai`)

- Evaluate both sides of the comparison as value expressions per the rules above.
- If evaluating either side of the condition itself hits a domain error (i.e. would
  produce NULL per §4), the condition cannot be reliably determined — the **overall
  row result is NULL** (do not silently default to false, since IEEE-754 comparisons
  against NaN are `false` for every operator, which would silently and incorrectly
  steer every such row into the `targil_false` branch).
- None of the formulas in the initial catalog can actually trigger this (conditions
  only compare `a`, `b`, `c`, `d` and simple arithmetic on them, which are always
  finite), but the rule is stated so it's a decision, not a gap, if a future formula
  needs it.
- Otherwise, evaluate `targil` if true, `targil_false` if false. That branch's
  result is subject to the same §4 domain-error rule independently.

## 6. Cross-engine comparison tolerance

Two `double` values `x` and `y` (or a value and a persisted result) are considered
equal if:

```
abs(x - y) <= 1e-9 * max(abs(x), abs(y), 1.0)
```

The `1.0` floor makes this behave as an **absolute** tolerance of `1e-9` when both
values are smaller than 1 in magnitude, and a **relative** tolerance of `1e-9`
otherwise — this avoids the classic failure mode of pure relative tolerance
rejecting two values that are both legitimately close to zero (e.g. `1e-16` vs
`-1e-16`, which are equal for any practical purpose but have an undefined/huge
relative difference against each other).

**NULL must match NULL exactly.** NULL vs. any non-NULL numeric value is always a
mismatch, regardless of tolerance.

## 7. Checksums (how 1,000,000 rows get verified without persisting 1,000,000 rows per engine)

For a given `(targil_id, method)` pair, after evaluating all 1,000,000 rows:

```
checksum  = sum of every non-NULL result, computed in float64
null_count = count of rows whose result is NULL
```

Two engines agree on a formula if:

1. `null_count` matches **exactly** (it's an integer — no tolerance applies), **and**
2. `checksum` matches within the §6 tolerance.

**Known, accepted source of tiny checksum drift:** the five engines sum results in
different orders — `numpy_engine.py` does a vectorized reduction, T-SQL's `SUM()`
picks its own internal order, the row-by-row engines sum in `data_id` order, etc.
Floating-point addition is not associative, so bit-identical checksums across
engines are not guaranteed even when every individual row matches. This is exactly
why §6 uses a tolerance for the checksum comparison too, rather than exact equality
— call this out in `REPORT.md` rather than treating it as a bug if it occurs.

Both `checksum` and `null_count` are written to `t_log` per `(targil_id, method)`
per run — this is the full-dataset verification. The 10,000-row sample in
`t_results` (see Step 6 of the brief) is the row-level, `(data_id, targil_id)`-keyed
verification; the two are independent checks and both must pass.

## 8. Summary table (translation targets)

| Concept | Python (`eval`) | NumPy | C# (Expression Trees) | T-SQL |
|---|---|---|---|---|
| Identifiers | local vars `a,b,c,d` (`float`) | columns as `np.ndarray[float64]` | `ParameterExpression` per column | `@a FLOAT, @b FLOAT, ...` via `sp_executesql` params |
| `NULL` result | Python `None` | `np.nan` in array, translated to `NULL` at write time | `double?` = `null` | SQL `NULL` |
| Domain guard | `try/except` + `isnan/isinf` check | `np.errstate` + `isnan`/`isinf` mask | `IsNaN`/`IsInfinity` check | explicit `CASE WHEN` / `NULLIF` |

---

This document is the ground truth. If `compare_results.py` reports a mismatch,
the first question is "which engine violated SEMANTICS.md," not "what tolerance do
we need to loosen."
