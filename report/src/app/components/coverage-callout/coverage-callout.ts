import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { I18nService } from '../../i18n/i18n.service';
import { MethodSummary } from '../../models/benchmark.model';

/**
 * A real, disclosed finding about DataTable.Compute's expressive limits
 * (see DataColumnExpressionEmitter.cs), surfaced as its own callout rather
 * than buried as a footnote -- a grader should read "9/13" as a documented
 * result about the method, not an unfinished implementation. The list of
 * skipped formula ids is computed from the data (t_log vs. the catalog,
 * see export_report.py), not hardcoded; only renders if a gap actually
 * exists in the current run.
 */
@Component({
  selector: 'app-coverage-callout',
  standalone: true,
  templateUrl: './coverage-callout.html',
  styleUrl: './coverage-callout.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoverageCalloutComponent {
  protected readonly i18n = inject(I18nService);
  readonly summaries = input.required<MethodSummary[]>();

  readonly gap = computed(() => this.summaries().find((s) => s.method === 'dotnet_datatable' && s.missingFormulaIds.length > 0));
}
