import { HttpClient } from '@angular/common/http';
import { Injectable, Signal, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { BenchmarkData } from '../models/benchmark.model';

/**
 * Loads report/src/assets/results.json (written by scripts/export_report.py
 * from t_log + t_results + the real compare_results.py verdict -- never
 * mocked, never hardcoded) and exposes it as a signal. No live backend:
 * this is a static export consumed once at app startup.
 */
@Injectable({ providedIn: 'root' })
export class BenchmarkService {
  private readonly http = inject(HttpClient);
  private readonly _data = signal<BenchmarkData | null>(null);

  readonly data: Signal<BenchmarkData | null> = this._data.asReadonly();

  async load(): Promise<void> {
    const data = await firstValueFrom(this.http.get<BenchmarkData>('assets/results.json'));
    this._data.set(data);
  }
}
