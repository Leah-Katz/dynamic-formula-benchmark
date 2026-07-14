import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { ChartConfiguration } from 'chart.js';
import { ChartComponent } from '../chart/chart';
import { I18nService } from '../../i18n/i18n.service';
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
  protected readonly i18n = inject(I18nService);
  readonly runs = input.required<MethodRun[]>();

  readonly config = computed<ChartConfiguration>(() => {
    const methods = Object.keys(METHOD_META).filter((m) => this.runs().some((r) => r.method === m));
    const rtl = this.i18n.locale() === 'he';
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
            label: this.i18n.t('breakdown.compile'),
            data: totals.map((t) => t.compile),
            backgroundColor: cssVar('--phase-compile'),
            stack: 'phases',
          },
          {
            label: this.i18n.t('breakdown.eval'),
            data: totals.map((t) => t.eval),
            backgroundColor: cssVar('--phase-eval'),
            stack: 'phases',
          },
          {
            label: this.i18n.t('breakdown.persist'),
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
        rtl,
        scales: {
          x: {
            stacked: true,
            title: { display: true, text: this.i18n.t('breakdown.xAxis') },
            grid: { color: 'rgba(137,135,129,0.2)' },
            reverse: rtl,
          },
          y: { stacked: true, grid: { display: false }, position: rtl ? 'right' : 'left' },
        },
        plugins: {
          legend: { position: 'bottom', rtl, textDirection: rtl ? 'rtl' : 'ltr' },
          tooltip: {
            rtl,
            textDirection: rtl ? 'rtl' : 'ltr',
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${(ctx.raw as number)?.toFixed(1)} ${this.i18n.t('common.msUnit')}`,
            },
          },
        },
      },
    };
  });
}
