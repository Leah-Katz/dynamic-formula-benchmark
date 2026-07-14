import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
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
}
