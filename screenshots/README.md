# Screenshots checklist

Grading deliverable — capture these and drop them in this folder (PNG, descriptive
filenames like `01-ssms-tables.png`).

- [ ] **SSMS: `t_data`** — Object Explorer showing the table, plus a `SELECT TOP 100
      * FROM t_data` result grid (or `SELECT COUNT(*)` showing 1,000,000).
- [ ] **SSMS: `t_targil`** — full 13-row formula catalog (`SELECT * FROM t_targil
      ORDER BY targil_id`).
- [ ] **SSMS: `t_results`** — a sample of rows for at least two different `method`
      values on the same `targil_id`, showing matching `result` values.
- [ ] **SSMS: `t_log`** — rows for all 5 methods on the same `targil_id`, showing
      `compile_ms` / `eval_ms` / `persist_ms` / `checksum` / `null_count`.
- [ ] **`python scripts/compare_results.py` console output** — the full pass/fail
      matrix and the final "All methods produced identical results" line.
- [ ] **`python run_all.py` console output** — enough of it to show all 5 engines
      ran and the pipeline completed (start + end of the log is fine, doesn't need
      to be the full 200+ lines).
- [ ] **The deployed report** — the full dashboard (correctness badge, winner
      callout, complexity chart, runtime chart, breakdown chart, summary table)
      loaded from the live GitHub Pages URL, not `localhost`.
- [ ] **`--persist=full` proof** — console output showing an engine run with
      `--persist=full`, plus a `SELECT COUNT(*) FROM t_results WHERE method = '...'`
      showing 1,000,000 rows for that method.
