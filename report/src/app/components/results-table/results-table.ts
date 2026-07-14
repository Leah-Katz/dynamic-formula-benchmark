import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { I18nService } from '../../i18n/i18n.service';
import { MethodSummary } from '../../models/benchmark.model';
import { methodColor } from '../../models/method-meta';

type SortKey = keyof Pick<MethodSummary, 'label' | 'totalRuntimeMs' | 'rowsPerSec' | 'speedupVsSlowest' | 'formulaCount'>;

@Component({
  selector: 'app-results-table',
  standalone: true,
  imports: [DecimalPipe],
  templateUrl: './results-table.html',
  styleUrl: './results-table.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ResultsTableComponent {
  protected readonly i18n = inject(I18nService);
  readonly summaries = input.required<MethodSummary[]>();

  readonly sortKey = signal<SortKey>('totalRuntimeMs');
  readonly sortAsc = signal<boolean>(true);

  readonly sorted = computed(() => {
    const key = this.sortKey();
    const asc = this.sortAsc();
    return [...this.summaries()].sort((a, b) => {
      const av = a[key];
      const bv = b[key];
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return asc ? cmp : -cmp;
    });
  });

  color(method: string): string {
    return methodColor(method);
  }

  setSort(key: SortKey): void {
    if (this.sortKey() === key) {
      this.sortAsc.update((v) => !v);
    } else {
      this.sortKey.set(key);
      this.sortAsc.set(true);
    }
  }

  sortIndicator(key: SortKey): string {
    if (this.sortKey() !== key) return '';
    return this.sortAsc() ? '▲' : '▼';
  }

  coverageTooltip(row: MethodSummary): string | null {
    if (row.missingFormulaIds.length === 0) return null;
    return this.i18n.t('table.coverageTooltip', { count: row.formulaCount, total: row.totalFormulaCount });
  }
}
