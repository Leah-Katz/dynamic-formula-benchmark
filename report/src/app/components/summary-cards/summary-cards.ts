import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MethodSummary, Winner } from '../../models/benchmark.model';
import { methodLabel } from '../../models/method-meta';

@Component({
  selector: 'app-summary-cards',
  standalone: true,
  imports: [DecimalPipe],
  templateUrl: './summary-cards.html',
  styleUrl: './summary-cards.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SummaryCardsComponent {
  readonly summaries = input.required<MethodSummary[]>();
  readonly winner = input.required<Winner>();
  readonly formulaCount = input.required<number>();

  readonly winnerLabel = computed(() => methodLabel(this.winner().method));

  readonly slowest = computed(() =>
    [...this.summaries()].sort((a, b) => b.totalRuntimeMs - a.totalRuntimeMs)[0],
  );

  readonly fastest = computed(() =>
    [...this.summaries()].sort((a, b) => a.totalRuntimeMs - b.totalRuntimeMs)[0],
  );

  readonly maxSpeedup = computed(() => {
    const s = this.slowest();
    const f = this.fastest();
    return s && f && f.totalRuntimeMs > 0 ? s.totalRuntimeMs / f.totalRuntimeMs : 0;
  });
}
