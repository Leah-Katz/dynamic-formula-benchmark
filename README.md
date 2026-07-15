# Dynamic Formula Evaluation Benchmark

### מטלת בית לתפקיד מפתח/ת בכיר/ה, משרד החינוך

**[Summary Report](REPORT.md)** ([עברית](REPORT.he.md)) &nbsp;|&nbsp; **[Live Demo](https://leah-katz.github.io/dynamic-formula-benchmark/)**

---

## Overview

מערכת תשלומים מחשבת מאות סוגי תשלום לפי נוסחאות שמשתנות עם הזמן (הסכמים חדשים, חוקים
חדשים, תעריפים חדשים). הפרויקט הזה קורא נוסחאות כאלה ממסד נתונים בזמן ריצה — לא כקוד
קשיח — ומחשב אותן בעזרת חמישה מנועים שונים, כל אחד באסטרטגיית מימוש נפרדת. תוצאות
החישוב וזמני הריצה נשמרים במסד הנתונים, מוצלבים בין כל המנועים לאימות נכונות, ומוצגים
בלוח מחוונים.

**היקף:** 13 נוסחאות × 1,000,000 שורות × 5 מנועי חישוב.

## Architecture

```
 +------------------------------------------------------------------+
 |                    SQL Server -- PaymentSystem                   |
 |   t_data (1,000,000 rows)   t_targil (13 formulas)   t_sample    |
 +------------------------------------+-----------------------------+
                                       |
      +-------------+-------------+---+---------+-------------+
      v             v             v             v             v
 python_eval   python_numpy  dotnet_data-  dotnet_expr-     sql_sp
 (eval_engine  (numpy_engine  table         tree           (02_sp_calc_
  .py --        .py --        (DataTable-  (ExpressionTrees formula.sql,
  per-row       vectorized     Compute --   -- compiled      set-based,
  eval())       NumPy array)   naive        delegate,        sp_executesql)
                                baseline)    JIT-compiled)
      |             |             |             |             |
      +-------------+-------------+------+------+-------------+
                                          |
                                          v
                      t_results (sample / full)  +  t_log (timings)
                                          |
                                          v
                      scripts/compare_results.py  (cross-engine verification)
                      scripts/export_report.py    (-> report/public/assets/results.json)
                                          |
                                          v
                      report/  --  Angular dashboard (GitHub Pages)
```

כל מנוע מאמת את הנוסחה בעזרת מפענח (parser) משלו לפני שהוא בכלל מחשב אותה — ראו
"How Each Engine Works" למטה.

## Stack

| Layer | Technology |
|---|---|
| Database | SQL Server 2025 Developer Edition, T-SQL (`sp_executesql`) |
| Compute — C# | .NET 10 (`net10.0`), `System.Data.DataTable`, `System.Linq.Expressions` |
| Compute — Python | Python 3.13, `pyodbc`, NumPy |
| Report UI | Angular 22 (standalone components, TypeScript strict), Chart.js 4.5.1 |
| Orchestration | `run_all.py`, `sqlcmd` |
| Deployment | GitHub Pages via `angular-cli-ghpages` |

## Project Structure

```
PaymentSystem/
├── config.py                     # single source of truth: Python DB connection string
├── requirements.txt               # pyodbc, numpy
├── run_all.py                     # one command: schema → seed → all 5 engines → compare → export
├── SEMANTICS.md                   # the cross-engine evaluation contract (grammar, NULL rules, tolerance)
├── REPORT.md / REPORT.he.md       # graded technical writeup (EN / HE)
│
├── sql/
│   ├── 01_schema.sql              # t_data, t_targil, t_results, t_sample, t_log
│   └── 02_sp_calc_formula.sql     # T-SQL recursive-descent parser + sp_calc_formula
│
├── scripts/
│   ├── seed_data.py                # generates + bulk-loads 1,000,000 rows (seed=42)
│   ├── seed_formulas.py            # loads the 13-formula catalog into t_targil
│   ├── compare_results.py          # row-level + full-dataset cross-engine verification
│   └── export_report.py            # writes report/public/assets/results.json
│
├── src/
│   ├── python/
│   │   ├── formula_parser.py       # shared AST-based whitelist validator
│   │   ├── persistence.py          # shared DB access + persistence strategy
│   │   ├── eval_engine.py          # engine: python_eval
│   │   └── numpy_engine.py         # engine: python_numpy
│   ├── sql/
│   │   └── run_sp.py               # driver for the T-SQL stored-procedure engine
│   └── dotnet/
│       ├── PaymentSystem.Shared/   # Config.cs, Db.cs, FormulaParser.cs (C# AST parser)
│       ├── DataTableCompute/       # engine: dotnet_datatable
│       └── ExpressionTrees/        # engine: dotnet_exprtree (the winner)
│
├── report/                         # Angular dashboard, deployed to GitHub Pages
│   └── src/app/
│       ├── i18n/                   # EN/HE translations + I18nService
│       ├── services/               # benchmark.service.ts
│       └── components/             # dashboard, correctness-badge, coverage-callout,
│                                    # formula-catalog, summary-cards, runtime-chart,
│                                    # complexity-chart, breakdown-chart, results-table,
│                                    # language-toggle, chart (shared Chart.js wrapper)
│
└── screenshots/                    # grading evidence (SSMS tables, script console output)
```

## Database Schema

חמש טבלאות — ארבע שהמטלה מגדירה במפורש, ועוד טבלת עזר אחת (`t_sample`) ליצוב המדגם בין
המנועים:

- **`t_data`** — `data_id INT PK, a/b/c/d FLOAT` — **1,000,000 שורות**, מקור נתוני הקלט.
- **`t_targil`** — `targil_id INT PK, targil VARCHAR(500), tnai VARCHAR(500) NULL, targil_false VARCHAR(500) NULL` — **13 שורות**, קטלוג הנוסחאות.
- **`t_sample`** — `data_id INT PK/FK` — **10,000 שורות**, המדגם הדטרמיניסטי המשותף שכל מנוע שומר עבורו תוצאות.
- **`t_results`** — `results_id IDENTITY PK, data_id FK, targil_id FK, method VARCHAR(50), result FLOAT NULL` — נצבר עם כל הרצה; כרגע 610,000 שורות (4 שיטות מכסות את כל 13 הנוסחאות × 10,000 שורות מדגם = 520,000, ועוד `dotnet_datatable` שמכסה רק 9 נוסחאות מתוך 13 × 10,000 = 90,000).
- **`t_log`** — `log_id IDENTITY PK, targil_id FK, method, run_time, rows_processed, compile_ms, eval_ms, persist_ms, checksum, null_count, run_ts` — שורה אחת לכל (נוסחה, שיטה) בכל הרצה; נצבר לאורך זמן.

## Formulas

13 הנוסחאות בקטלוג (`t_targil`), כפי שנקראות בפועל מהמסד:

**Simple**

| # | `targil` |
|---|---|
| 1 | `a + b` |
| 2 | `c * 2` |
| 3 | `b - a` |
| 4 | `d / 4` |

**Complex**

| # | `targil` |
|---|---|
| 5 | `(a + b) * 8` |
| 6 | `sqrt(c^2 + d^2)` |
| 7 | `log(b) + c` |
| 8 | `abs(d - b)` |
| 12 | `sqrt(abs((a + b) * (c - d)) + pow(a, 2))` |

**Conditional** (`tnai` → `targil` : `targil_false`)

| # | `tnai` | `targil` | `targil_false` |
|---|---|---|---|
| 9 | `a > 5` | `b * 2` | `b / 2` |
| 10 | `b < 10` | `a + 1` | `d - 1` |
| 11 | `a == c` | `1` | `0` |
| 13 | `sqrt(a^2 + b^2) > c` | `(a + b + c + d) / 4` | `max(a, b)` |

## How Each Engine Works

**כל חמשת המנועים חולקים עיקרון אחד: הנוסחה מגיעה ממסד נתונים, כלומר מחוץ לגבול האמון
של התוכנית, ולכן כל מנוע מריץ אותה דרך מפענח (parser) משלו שבודק רשימה סגורה של מזהים
מותרים (`a`,`b`,`c`,`d`, הפונקציות `sqrt`/`log`/`abs`/`min`/`max`/`pow`) לפני שהיא בכלל
נגישה ל-`eval()`, לביטוי NumPy, לעץ ביטויים מהודר, או ל-`sp_executesql`.** זהו לא regex —
זוהי הליכה אמיתית על עץ תחביר (`formula_parser.py` ב-Python, `FormulaParser.cs` ב-C#,
ופרוצדורות `sp_pf_*` שמממשות מפענח recursive-descent אמיתי גם ב-T-SQL).

- **`dotnet_exprtree` (C# ExpressionTrees) — השיטה המנצחת.** כל נוסחה מהודרת פעם אחת
  לעץ `System.Linq.Expressions` ומתקמפלת (JIT) לנציג (delegate) native. כל שורה
  לאחר מכן היא קריאת פונקציה ישירה — בלי פענוח חוזר, בלי dispatch של אינטרפרטר.
  **844 ms** זמן חישוב על פני 13 מיליון הערכות-שורה.
- **`sql_sp` (T-SQL `sp_executesql`).** חישוב מבוסס-קבוצות (set-based) שמתבצע כולו בתוך
  מנוע מסד הנתונים — הנוסחה מתורגמת לביטוי SQL בודד עם שומרי `CASE WHEN`/`NULLIF`
  לטיפול בשגיאות תחום, ומחושבת בפקודת `SELECT` אחת על פני כל 1,000,000 השורות.
- **`python_numpy` (Python NumPy).** כל נוסחה מתורגמת פעם אחת למחרוזת מקור של NumPy,
  ואז מחושבת כפעולת מערך אחת על פני כל העמודה, במקום לולאה על כל שורה בנפרד —
  **234 ms** זמן חישוב, קרוב לזמן של C# המהודר למרות ריצה בשפה מתפרשנת, כי
  האריתמטיקה בפועל מתבצעת במימוש ה-C של NumPy.
- **`python_eval` (Python `eval()`) — הבסיס האיטי במכוון.** `eval()` על אובייקט קוד
  שהודר מראש, נקרא בנפרד לכל שורה — **56,596 ms** זמן חישוב, שני סדרי גודל איטי יותר,
  כי כל שורה משלמת מחדש את מלוא ה-overhead של אינטרפרטר CPython.
- **`dotnet_datatable` (C# DataTable.Compute) — הבסיס הנאיבי.** `DataColumn.Expression`
  מפענחת את מחרוזת הביטוי מחדש בכל קריאה, בלי שלב הידור בכלל. חמור מכך: לשפת הביטויים
  שלה **אין בכלל `Sqrt`, `Log` או `Pow`/`^`** — עובדה שאומתה ישירות מול ה-runtime, לא
  הונחה. 4 מתוך 13 הנוסחאות **בלתי ניתנות לביטוי** בשיטה הזו ומדולגות עם סיבה מתועדת.
  ראו `REPORT.md` §1 לראיות המלאות (סוג החריגה, ההודעה המדויקת, וההפניה לדקדוק הרשמי
  של Microsoft).

## Prerequisites & Setup

- **Windows**, SQL Server 2025 Developer Edition (או 2022+; `LEAST`/`GREATEST` דורשים 2022+), instance מקומי, Windows Authentication
- **ODBC Driver 18 for SQL Server**
- **Python 3.11+** עם `pyodbc`, `numpy` (`pip install -r requirements.txt`)
- **.NET SDK** — הפרויקט מכוון ל-**net10.0** (ראו `Notes` למטה לגבי החריגה מ-net8.0 המקורי)
- **Node.js 20+** / npm — עבור אפליקציית ה-Angular בלבד

בדיקת סביבה:

```
sqlcmd -S localhost -E -C -Q "SELECT @@VERSION"
```

יצירת מסד הנתונים (פעם אחת):

```sql
CREATE DATABASE PaymentSystem;
ALTER DATABASE PaymentSystem SET RECOVERY SIMPLE;
```

**הרצת הכול בפקודה אחת** (משחזרת כל מספר ב-`REPORT.md` ממסד נתונים נקי, כ-3.5 דקות):

```
pip install -r requirements.txt
python run_all.py
```

**או שלב אחרי שלב:**

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

**הרצת אפליקציית ה-Angular מקומית:**

```
cd report
npm install
ng serve
```

פותחים את `http://localhost:4200`. האפליקציה טוענת את `public/assets/results.json`
בעליית המערכת — יש לחדש אותו עם `python scripts/export_report.py` אחרי כל הרצה חדשה.

## Performance Characteristics

| Method | Strength | Trade-off | Best For |
|---|---|---|---|
| **C# ExpressionTrees** | המהיר ביותר: 2,949 ms, 4.4M שורות/שנייה, פי 26 מהיר יותר מהבסיס האיטי | כמעט ואין — גם המהיר וגם התחזוקתי ביותר | פרודקשן — **השיטה המומלצת** |
| T-SQL `sp_executesql` | אפס העברת נתונים ברשת; זמן חישוב תחרותי | שלב השמירה איטי (6,330 ms) כי אין תוצאה בזיכרון לשימוש חוזר; ~400 שורות T-SQL קשות לתחזוקה | כשהלוגיקה חייבת לשבת בתוך שכבת מסד הנתונים |
| Python NumPy | מהירות קרובה ל-C# (234 ms חישוב) למרות שפה מתפרשנת | כמו כל מנוע מגובה-DB, זמן השמירה שולט (13,446 ms) | פיתוח מהיר במחסנית מבוססת-Python |
| C# DataTable.Compute | — (זהו הבסיס הנאיבי שהמטלה מבקשת) | **לא מסוגל לבטא `sqrt`/`log` בכלל** — פסילה מבחינת יכולת ביטוי, לא רק איטיות (פי 13 איטי יותר גם על מה שהוא כן מריץ) | לא מומלץ — נכלל כבסיס השוואה |
| Python `eval()` | — (זהו הבסיס האיטי במכוון) | שני סדרי גודל איטי יותר (77,100 ms סה"כ) — overhead מלא של אינטרפרטר לכל שורה | לא מומלץ — נכלל כבסיס השוואה |

**המלצה:** עצי ביטוי מהודרים (Expression Trees) — או נציג (delegate) מהודר-JIT מקביל
בכל מחסנית טכנולוגית — עם מאמת הנוסחאות המשותף כשער חובה לפני שנוסחה כלשהי מגיעה
לפרודקשן. פירוט מלא של הפשרות ב-`REPORT.md` §4.

## Notes

- **שגיאות תחום → NULL.** חלוקה באפס, `sqrt` של מספר שלילי, `log` של מספר לא-חיובי —
  בכל חמשת המנועים, אלה מפיקים `NULL`, לא חריגה ולא `NaN`/אינסוף. הכלל המלא ב-`SEMANTICS.md` §4.
- **אסטרטגיית השמירה (persist).** כברירת מחדל כל מנוע מחשב על פני כל 1,000,000
  השורות אך שומר רק את המדגם הדטרמיניסטי המשותף של 10,000 שורות (`t_sample`) — אחרת
  5 מנועים × 13 נוסחאות × 1M שורות היו כ-65 מיליון שורות כתיבה בכל הרצה. כל מנוע
  מקבל גם `--persist=full` לכתיבת כל 1,000,000 השורות כהוכחת-קונספט מלאה
  (למשל: `python -m src.python.eval_engine --persist=full`).
- **חיבור למסד הנתונים.** מוגדר במקום אחד לכל שפה: `config.py` (Python, syntax של
  ODBC) ו-`src/dotnet/PaymentSystem.Shared/Config.cs` (C#, syntax של ADO.NET) — שניהם
  קוראים משתנה סביבה קודם (`PAYMENTSYSTEM_CONNECTION_STRING` /
  `PAYMENTSYSTEM_CONNECTION_STRING_DOTNET`) ונופלים חזרה לברירת מחדל מקומית.
- **.NET 10, לא .NET 8.** הפרויקט תוכנן במקור ל-`net8.0`, אך רק .NET 10 SDK/runtime
  היו זמינים בסביבת הפיתוח — שינוי מוצהר ומאושר, לא חריגה שקטה (ראו היסטוריית git).
  מי שיש לו .NET 8 ורוצה להתאים למפרט המקורי יכול לשנות את `TargetFramework` בשלושת
  קובצי ה-`.csproj` תחת `src/dotnet/` בחזרה ל-`net8.0`.
- **בנייה ב-Windows + Git Bash: היזהרו מ-MSYS path conversion.** ארגומנט שמתחיל ב-`/`
  כמו `--base-href /dynamic-formula-benchmark/` עלול להיהפך בטעות לנתיב Windows.
  אם זה קורה, הריצו עם `MSYS_NO_PATHCONV=1` לפני הפקודה.
