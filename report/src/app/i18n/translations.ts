export type Locale = 'en' | 'he';

/**
 * Flat, dotted-key translation dictionary for both supported locales.
 * Formula strings (targil/tnai/targil_false) and method identifiers
 * (python_eval, sql_sp, ...) are deliberately NOT here -- they're data,
 * not UI copy, and stay untranslated everywhere they're rendered.
 *
 * {placeholder} tokens are replaced by I18nService.t(key, params).
 */
export const TRANSLATIONS: Record<Locale, Record<string, string>> = {
  en: {
    'app.title': 'Dynamic Formula Evaluation Benchmark',
    'app.subtitle':
      '{count} formulas × 1,000,000 rows, evaluated by 5 engines (Python eval(), NumPy, ' +
      'C# DataTable.Compute, C# Expression Trees, T-SQL sp_executesql) and cross-verified for correctness.',

    'lang.toggleLabel': 'Language',

    'badge.allAgree': 'All methods agree',
    'badge.mismatch': 'Mismatch detected',
    'badge.detailPass': 'All 5 methods produced identical results (tolerance {tolerance})',
    'badge.detailFail': '{rowFail} row-level and {fullFail} full-dataset mismatch(es) found',
    'badge.naNote':
      '{count} formula/method combination(s) marked N/A — documented limitation ' +
      '(DataTable.Compute cannot express sqrt/log, see the coverage finding below), not a failure',

    'summary.recommended': 'Recommended method',
    'summary.formulasBenchmarked': 'Formulas benchmarked',
    'summary.fastestTotal': 'Fastest total runtime ({label})',
    'summary.slowestTotal': 'Slowest total runtime ({label})',
    'summary.spread': 'Spread: fastest vs. slowest',

    'coverage.title': 'Finding: DataTable.Compute cannot express every formula',
    'coverage.body':
      "System.Data's DataColumn.Expression grammar has no Sqrt, Log, or Pow/^ at all — verified " +
      'directly against this .NET runtime, not assumed (see REPORT.md §1). 4 of the 13 formulas ' +
      '(#6, #7, #12, #13) are skipped for this method rather than faked with an incorrect workaround, ' +
      'because faking them would invalidate the cross-engine correctness comparison. This is a real, ' +
      "disclosed result about the method's expressive limits — not an unfinished implementation.",
    'coverage.skippedLabel': 'Skipped formulas:',
    'coverage.reasonSqrt': 'no Sqrt() function',
    'coverage.reasonLog': 'no Log() function',
    'coverage.coverageLabel': 'Coverage: {covered} / {total} formulas',

    'table.method': 'Method',
    'table.formulas': 'Formulas',
    'table.totalRuntime': 'Total runtime',
    'table.rowsPerSec': 'Rows/sec',
    'table.speedup': 'Speedup vs. slowest',
    'table.coverageTooltip':
      '{count} / {total} formulas — DataColumn.Expression cannot express sqrt/log ' +
      '(see the coverage finding above)',

    'common.logScale': 'Log scale',
    'common.msUnit': 'ms',

    'category.simple': 'Simple',
    'category.complex': 'Complex',
    'category.conditional': 'Conditional',

    'complexity.title': 'Does the ranking change as formulas get more complex?',
    'complexity.subtitle': 'Average run time per formula, grouped by simple / complex / conditional',
    'complexity.yAxis': 'Avg. run time per formula (ms, log scale)',
    'complexity.yAxisLinear': 'Avg. run time per formula (ms)',

    'runtime.title': 'Run time per method, per formula',
    'runtime.xAxis': 'Formula (targil_id)',
    'runtime.yAxis': 'Run time (ms, log scale)',
    'runtime.yAxisLinear': 'Run time (ms)',

    'breakdown.title': 'Compile / eval / persist breakdown',
    'breakdown.note':
      "T-SQL sp_executesql's eval and persist phases each independently re-scan and re-evaluate the " +
      'formula (no shared in-memory result between statements) — its breakdown is not a clean ' +
      'apples-to-apples decomposition against the other four methods. See REPORT.md.',
    'breakdown.compile': 'Compile',
    'breakdown.eval': 'Eval',
    'breakdown.persist': 'Persist',
    'breakdown.xAxis': 'Total time (ms)',

    'catalog.title': 'Formula catalog',
    'catalog.subtitle': 'All {count} formulas benchmarked, read directly from t_targil',
    'catalog.colId': '#',
    'catalog.colFormula': 'Formula (targil)',
    'catalog.colCondition': 'Condition (tnai)',
    'catalog.colFalseBranch': 'If false (targil_false)',
    'catalog.colCategory': 'Category',
    'catalog.none': '—',

    'dashboard.summaryTable': 'Summary table',
    'dashboard.loading': 'Loading benchmark results…',
  },
  he: {
    'app.title': "בנצ'מרק להערכת נוסחאות דינמיות",
    'app.subtitle':
      '{count} נוסחאות × 1,000,000 שורות, מחושבות על ידי 5 מנועים (Python eval(), NumPy, ' +
      'C# DataTable.Compute, C# Expression Trees, T-SQL sp_executesql) ומאומתות הצלבה מול כל המנועים לבדיקת נכונות.',

    'lang.toggleLabel': 'שפה',

    'badge.allAgree': 'כל השיטות מסכימות',
    'badge.mismatch': 'אותרה אי-התאמה',
    'badge.detailPass': 'כל 5 השיטות הפיקו תוצאות זהות (סף סטייה {tolerance})',
    'badge.detailFail':
      'אותרו {rowFail} אי-התאמות ברמת השורה ו-{fullFail} אי-התאמות במלוא מערך הנתונים',
    'badge.naNote':
      '{count} צירופי נוסחה/שיטה מסומנים כ-"לא רלוונטי" — מגבלה מתועדת ' +
      '(ל-DataTable.Compute אין אפשרות לבטא sqrt/log, ראו את הממצא למטה), ולא כישלון',

    'summary.recommended': 'השיטה המומלצת',
    'summary.formulasBenchmarked': 'נוסחאות שנבדקו',
    'summary.fastestTotal': 'זמן ריצה כולל מהיר ביותר ({label})',
    'summary.slowestTotal': 'זמן ריצה כולל איטי ביותר ({label})',
    'summary.spread': 'טווח: מהיר מול איטי',

    'coverage.title': 'ממצא: ל-DataTable.Compute אין אפשרות לבטא כל נוסחה',
    'coverage.body':
      'לדקדוק הביטויים של DataColumn.Expression ב-System.Data אין בכלל פונקציות Sqrt, Log או Pow/^ — דבר שאומת בבדיקה ישירה מול ה-runtime של .NET הזה, ולא הנחה (ראו REPORT.md §1). 4 מתוך 13 הנוסחאות (#6, #7, #12, #13) מדולגות עבור שיטה זו במקום להתחזות עם עקיפה שגויה, משום שהתחזות כזו היתה פוגעת בהשוואת הנכונות בין המנועים. זהו ממצא אמיתי ומוצהר בגלוי על מגבלות הביטוי של השיטה — ולא יישום לא גמור.',
    'coverage.skippedLabel': 'נוסחאות שדולגו:',
    'coverage.reasonSqrt': 'אין פונקציית ()Sqrt',
    'coverage.reasonLog': 'אין פונקציית ()Log',
    'coverage.coverageLabel': 'כיסוי: {covered} מתוך {total} נוסחאות',

    'table.method': 'שיטה',
    'table.formulas': 'נוסחאות',
    'table.totalRuntime': 'זמן ריצה כולל',
    'table.rowsPerSec': 'שורות/שנייה',
    'table.speedup': 'פי מהירות מול האיטי ביותר',
    'table.coverageTooltip':
      '{count} מתוך {total} נוסחאות — ל-DataColumn.Expression אין אפשרות לבטא sqrt/log ' +
      '(ראו את הממצא למעלה)',

    'common.logScale': 'סולם לוגריתמי',
    'common.msUnit': 'ms',

    'category.simple': 'פשוטה',
    'category.complex': 'מורכבת',
    'category.conditional': 'מותנית',

    'complexity.title': 'האם הדירוג משתנה ככל שהנוסחאות מורכבות יותר?',
    'complexity.subtitle': 'זמן ריצה ממוצע לנוסחה, מקובץ לפי פשוטה / מורכבת / מותנית',
    'complexity.yAxis': 'זמן ריצה ממוצע לנוסחה (ms, סולם לוגריתמי)',
    'complexity.yAxisLinear': 'זמן ריצה ממוצע לנוסחה (ms)',

    'runtime.title': 'זמן ריצה לפי שיטה, לכל נוסחה',
    'runtime.xAxis': 'נוסחה (targil_id)',
    'runtime.yAxis': 'זמן ריצה (ms, סולם לוגריתמי)',
    'runtime.yAxisLinear': 'זמן ריצה (ms)',

    'breakdown.title': 'פילוח זמן: הידור / חישוב / שמירה',
    'breakdown.note':
      'שלבי החישוב והשמירה של T-SQL sp_executesql סורקים ומחשבים מחדש את הנוסחה באופן עצמאי (אין תוצאה משותפת בזיכרון בין הפקודות) — הפילוח שלה אינו פירוק נקי מול ארבעת השיטות האחרות. ראו REPORT.md.',
    'breakdown.compile': 'הידור',
    'breakdown.eval': 'חישוב',
    'breakdown.persist': 'שמירה',
    'breakdown.xAxis': 'זמן כולל (ms)',

    'catalog.title': 'קטלוג הנוסחאות',
    'catalog.subtitle': 'כל {count} הנוסחאות שנבדקו, כפי שנקראו ישירות מ-t_targil',
    'catalog.colId': '#',
    'catalog.colFormula': 'נוסחה (targil)',
    'catalog.colCondition': 'תנאי (tnai)',
    'catalog.colFalseBranch': 'אם לא מתקיים (targil_false)',
    'catalog.colCategory': 'קטגוריה',
    'catalog.none': '—',

    'dashboard.summaryTable': 'טבלת סיכום',
    'dashboard.loading': "טוען תוצאות בנצ'מרק…",
  },
};
