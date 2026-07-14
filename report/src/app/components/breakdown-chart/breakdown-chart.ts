import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { ChartConfiguration } from 'chart.js';
import { ChartComponent } from '../chart/chart';
import { MethodRun } from '../../models/benchmark.model';
import { METHOD_META, methodLabel } from '../../models/method-meta';

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Compile / eval / persist breakdown, stacked per method, summed across
 * every formula that method covers. sql_sp's eval and persist phases are
 * not a clean decomposition of one shared compute pass (each statement
 * independently re-scans/re-evaluates the formula -- see
 * sql/02_sp_calc_formula.sql and REPORT.md) -- called out under the chart
 * rather than presented as directly equivalent to the other four methods.
 */
@Component({
  selector: 'app-breakdown-chart',
  standalone: true,
  imports: [ChartComponent],
  templateUrl: './breakdown-chart.html',
  styleUrl: './breakdown-chart.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BreakdownChartComponent {
  readonly runs = input.required<MethodRun[]>();

  readonly config = computed<ChartConfiguration>(() => {
    const methods = Object.keys(METHOD_META).filter((m) => this.runs().some((r) => r.method === m));
    const totals = methods.map((method) => {
      const rows = this.runs().filter((r) => r.method === method);
      return {
        compile: rows.reduce((s, r) => s + r.compileMs, 0),
        eval: rows.reduce((s, r) => s + r.evalMs, 0),
        persist: rows.reduce((s, r) => s + r.persistMs, 0),
      };
    });

    return {
      type: 'bar',
      data: {
        labels: methods.map(methodLabel),
        datasets: [
          {
            label: 'Compile',
            data: totals.map((t) => t.compile),
            backgroundColor: cssVar('--phase-compile'),
            stack: 'phases',
          },
          {
            label: 'Eval',
            data: totals.map((t) => t.eval),
            backgroundColor: cssVar('--phase-eval'),
            stack: 'phases',
          },
          {
            label: 'Persist',
            data: totals.map((t) => t.persist),
            backgroundColor: cssVar('--phase-persist'),
            stack: 'phases',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        interaction: { mode: 'nearest', intersect: false },
        scales: {
          x: { stacked: true, title: { display: true, text: 'Total time (ms)' }, grid: { color: 'rgba(137,135,129,0.2)' } },
          y: { stacked: true, grid: { display: false } },
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
}
