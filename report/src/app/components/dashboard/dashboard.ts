import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { I18nService } from '../../i18n/i18n.service';
import { BenchmarkService } from '../../services/benchmark.service';
import { CorrectnessBadgeComponent } from '../correctness-badge/correctness-badge';
import { CoverageCalloutComponent } from '../coverage-callout/coverage-callout';
import { SummaryCardsComponent } from '../summary-cards/summary-cards';
import { RuntimeChartComponent } from '../runtime-chart/runtime-chart';
import { ComplexityChartComponent } from '../complexity-chart/complexity-chart';
import { BreakdownChartComponent } from '../breakdown-chart/breakdown-chart';
import { ResultsTableComponent } from '../results-table/results-table';
import { FormulaCatalogComponent } from '../formula-catalog/formula-catalog';
import { LanguageToggleComponent } from '../language-toggle/language-toggle';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CorrectnessBadgeComponent,
    CoverageCalloutComponent,
    SummaryCardsComponent,
    RuntimeChartComponent,
    ComplexityChartComponent,
    BreakdownChartComponent,
    ResultsTableComponent,
    FormulaCatalogComponent,
    LanguageToggleComponent,
  ],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent implements OnInit {
  private readonly benchmarkService = inject(BenchmarkService);
  protected readonly i18n = inject(I18nService);
  readonly data = this.benchmarkService.data;

  ngOnInit(): void {
    void this.benchmarkService.load();
  }
}
