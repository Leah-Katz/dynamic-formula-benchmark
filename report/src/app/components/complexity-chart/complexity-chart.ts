import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { ChartConfiguration } from 'chart.js';
import { ChartComponent } from '../chart/chart';
import { I18nService } from '../../i18n/i18n.service';
import { FormulaCategory, FormulaResult, MethodRun } from '../../models/benchmark.model';
import { METHOD_META, methodColor, methodLabel } from '../../models/method-meta';

const CATEGORIES: FormulaCategory[] = ['simple', 'complex', 'conditional'];

/**
 * The most interesting question in the project: does the ranking between
 * methods change as formulas get more complex? Average run time per
 * formula, grouped by category, one bar group per method -- ranking
 * reversals between the "Simple" group and the "Complex"/"Conditional"
 * groups are the whole point of this chart.
 */
@Component({
  selector: 'app-complexity-chart',
  standalone: true,
  imports: [ChartComponent],
  templateUrl: './complexity-chart.html',
  styleUrl: './complexity-chart.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ComplexityChartComponent {
  protected readonly i18n = inject(I18nService);
  readonly runs = input.required<MethodRun[]>();
  readonly formulas = input.required<FormulaResult[]>();

  readonly logScale = signal(true);

  readonly config = computed<ChartConfiguration>(() => {
    const formulas = this.formulas();
    const methods = Object.keys(METHOD_META).filter((m) => this.runs().some((r) => r.method === m));
    const rtl = this.i18n.locale() === 'he';

    const datasets = methods.map((method) => ({
      label: methodLabel(method),
      data: CATEGORIES.map((cat) => {
        const ids = formulas.filter((f) => f.category === cat).map((f) => f.targilId);
        const values = ids
          .map((id) => this.runs().find((r) => r.method === method && r.targilId === id)?.runTimeMs)
          .filter((v): v is number => v !== undefined);
        return values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : null;
      }),
      backgroundColor: methodColor(method),
      borderRadius: 4,
      borderSkipped: false as const,
    }));

    return {
      type: 'bar',
      data: { labels: CATEGORIES.map((c) => this.i18n.t(`category.${c}`)), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'nearest', intersect: false },
        rtl,
        scales: {
          x: { grid: { display: false }, reverse: rtl },
          y: {
            type: this.logScale() ? 'logarithmic' : 'linear',
            title: { display: true, text: this.i18n.t(this.logScale() ? 'complexity.yAxis' : 'complexity.yAxisLinear') },
            grid: { color: 'rgba(137,135,129,0.2)' },
            position: rtl ? 'right' : 'left',
          },
        },
        plugins: {
          legend: { position: 'bottom', rtl, textDirection: rtl ? 'rtl' : 'ltr' },
          tooltip: {
            rtl,
            textDirection: rtl ? 'rtl' : 'ltr',
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${(ctx.raw as number)?.toFixed(1)} ${this.i18n.t('common.msUnit')} avg`,
            },
          },
        },
      },
    };
  });

  toggleScale(): void {
    this.logScale.update((v) => !v);
  }
}
