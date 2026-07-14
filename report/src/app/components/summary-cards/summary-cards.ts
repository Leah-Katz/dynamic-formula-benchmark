import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { I18nService } from '../../i18n/i18n.service';
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
  protected readonly i18n = inject(I18nService);
  readonly summaries = input.required<MethodSummary[]>();
  readonly winner = input.required<Winner>();
  readonly formulaCount = input.required<number>();

  readonly winnerLabel = computed(() => methodLabel(this.winner().method));

  readonly winnerJustification = computed(() =>
    this.i18n.locale() === 'he' ? this.winner().justificationHe : this.winner().justificationEn,
  );

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
