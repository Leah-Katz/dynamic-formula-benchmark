/**
 * Fixed method -> {label, color} mapping, shared by every chart and the
 * table so color always follows the same entity (the method) consistently
 * across the whole dashboard -- never reassigned per chart, never cycled.
 * Colors are the CSS custom properties defined in src/styles.scss.
 */
export interface MethodMeta {
  label: string;
  colorVar: string;
}

export const METHOD_META: Record<string, MethodMeta> = {
  python_eval: { label: 'Python eval()', colorVar: '--series-python-eval' },
  python_numpy: { label: 'Python NumPy', colorVar: '--series-python-numpy' },
  dotnet_datatable: { label: 'C# DataTable.Compute', colorVar: '--series-dotnet-datatable' },
  dotnet_exprtree: { label: 'C# ExpressionTrees', colorVar: '--series-dotnet-exprtree' },
  sql_sp: { label: 'T-SQL sp_executesql', colorVar: '--series-sql-sp' },
};

export function methodLabel(method: string): string {
  return METHOD_META[method]?.label ?? method;
}

export function methodColor(method: string): string {
  const varName = METHOD_META[method]?.colorVar;
  if (!varName) return '#898781';
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}
