import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { ChartConfiguration } from 'chart.js';
import { ChartComponent } from '../chart/chart';
import { FormulaResult, MethodRun } from '../../models/benchmark.model';
import { METHOD_META, methodColor, methodLabel } from '../../models/method-meta';

/**
 * Grouped bar chart of run time per method, per formula. The spread between
 * methods spans orders of magnitude (see summary-cards' fastest/slowest
 * spread stat) -- a linear axis flattens the fast methods to near-zero, so
 * a log-scale toggle is offered per the brief.
 */
@Component({
  selector: 'app-runtime-chart',
  standalone: true,
  imports: [ChartComponent],
  templateUrl: './runtime-chart.html',
  styleUrl: './runtime-chart.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RuntimeChartComponent {
  readonly runs = input.required<MethodRun[]>();
  readonly formulas = input.required<FormulaResult[]>();

  readonly logScale = signal(true);

  readonly config = computed<ChartConfiguration>(() => {
    const formulas = [...this.formulas()].sort((a, b) => a.targilId - b.targilId);
    const methods = Object.keys(METHOD_META).filter((m) => this.runs().some((r) => r.method === m));
    const labels = formulas.map((f) => `#${f.targilId}`);

    const datasets = methods.map((method) => ({
      label: methodLabel(method),
      data: formulas.map((f) => this.runs().find((r) => r.method === method && r.targilId === f.targilId)?.runTimeMs ?? null),
      backgroundColor: methodColor(method),
      borderRadius: 4,
      borderSkipped: false as const,
    }));

    return {
      type: 'bar',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'nearest', intersect: false },
        scales: {
          x: { title: { display: true, text: 'Formula (targil_id)' }, grid: { display: false } },
          y: {
            type: this.logScale() ? 'logarithmic' : 'linear',
            title: { display: true, text: 'Run time (ms, log scale)' },
            grid: { color: 'rgba(137,135,129,0.2)' },
          },
        },
        plugins: {
          legend: { position: 'bottom' },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${(ctx.raw as number)?.toFixed(1)} ms`,
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
