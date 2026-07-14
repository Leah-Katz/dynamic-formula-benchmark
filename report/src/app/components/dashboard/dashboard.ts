import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { BenchmarkService } from '../../services/benchmark.service';
import { CorrectnessBadgeComponent } from '../correctness-badge/correctness-badge';
import { SummaryCardsComponent } from '../summary-cards/summary-cards';
import { RuntimeChartComponent } from '../runtime-chart/runtime-chart';
import { ComplexityChartComponent } from '../complexity-chart/complexity-chart';
import { BreakdownChartComponent } from '../breakdown-chart/breakdown-chart';
import { ResultsTableComponent } from '../results-table/results-table';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CorrectnessBadgeComponent,
    SummaryCardsComponent,
    RuntimeChartComponent,
    ComplexityChartComponent,
    BreakdownChartComponent,
    ResultsTableComponent,
  ],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent implements OnInit {
  private readonly benchmarkService = inject(BenchmarkService);
  readonly data = this.benchmarkService.data;

  ngOnInit(): void {
    void this.benchmarkService.load();
  }
}
