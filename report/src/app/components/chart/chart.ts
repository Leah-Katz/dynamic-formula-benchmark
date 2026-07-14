import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  effect,
  input,
  viewChild,
} from '@angular/core';
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJs,
  ChartConfiguration,
  Legend,
  LinearScale,
  LogarithmicScale,
  Title,
  Tooltip,
} from 'chart.js';

ChartJs.register(BarController, BarElement, CategoryScale, LinearScale, LogarithmicScale, Title, Tooltip, Legend);

/**
 * Small reusable wrapper around Chart.js -- every chart in the dashboard
 * (runtime-chart, complexity-chart, breakdown-chart) renders through this
 * one component instead of talking to Chart.js directly. Takes the
 * Chart.js config as an input() and owns the canvas + Chart instance
 * lifecycle (create / update on config change / destroy).
 */
@Component({
  selector: 'app-chart',
  standalone: true,
  templateUrl: './chart.html',
  styleUrl: './chart.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChartComponent implements AfterViewInit, OnDestroy {
  readonly config = input.required<ChartConfiguration>();
  readonly heightPx = input<number>(320);

  private readonly canvasRef = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private instance: ChartJs | null = null;

  constructor() {
    effect(() => {
      const cfg = this.config();
      if (this.instance) {
        this.instance.config.data = cfg.data;
        this.instance.config.options = cfg.options;
        this.instance.update();
      }
    });
  }

  ngAfterViewInit(): void {
    this.instance = new ChartJs(this.canvasRef().nativeElement, this.config());
  }

  ngOnDestroy(): void {
    this.instance?.destroy();
  }
}
