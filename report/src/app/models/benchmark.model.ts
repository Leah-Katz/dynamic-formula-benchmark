export type FormulaCategory = 'simple' | 'complex' | 'conditional';

export interface FormulaResult {
  targilId: number;
  targil: string;
  tnai: string | null;
  targilFalse: string | null;
  category: FormulaCategory;
}

/** One (method, targil_id) row from t_log -- the most recent run of each. */
export interface MethodRun {
  method: string;
  targilId: number;
  runTimeMs: number;
  rowsProcessed: number;
  compileMs: number;
  evalMs: number;
  persistMs: number;
  checksum: number | null;
  nullCount: number;
  runTs: string;
}

export interface MethodSummary {
  method: string;
  label: string;
  totalRuntimeMs: number;
  totalRowsProcessed: number;
  rowsPerSec: number;
  speedupVsSlowest: number;
  formulaCount: number;
  totalFormulaCount: number;
  /** targil_ids with no run at all for this method -- computed from the
   * data (diffing the full catalog against t_log), never hardcoded. */
  missingFormulaIds: number[];
}

export interface ComparisonVerdict {
  allPass: boolean;
  tolerance: number;
  sampleSize: number;
  rowLevelPass: number;
  rowLevelFail: number;
  rowLevelNa: number;
  fullDatasetPass: number;
  fullDatasetFail: number;
  fullDatasetNa: number;
  generatedAt: string;
}

export interface Winner {
  method: string;
  justificationEn: string;
  justificationHe: string;
}

export interface BenchmarkData {
  formulas: FormulaResult[];
  runs: MethodRun[];
  summaries: MethodSummary[];
  verdict: ComparisonVerdict;
  winner: Winner;
}
