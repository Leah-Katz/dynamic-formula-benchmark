import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { ComparisonVerdict } from '../../models/benchmark.model';

@Component({
  selector: 'app-correctness-badge',
  standalone: true,
  templateUrl: './correctness-badge.html',
  styleUrl: './correctness-badge.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CorrectnessBadgeComponent {
  readonly verdict = input.required<ComparisonVerdict>();

  readonly statusLabel = computed(() => (this.verdict().allPass ? 'All methods agree' : 'Mismatch detected'));

  readonly detail = computed(() => {
    const v = this.verdict();
    return v.allPass
      ? `All 5 methods produced identical results (tolerance ${v.tolerance.toExponential(0)})`
      : `${v.rowLevelFail} row-level and ${v.fullDatasetFail} full-dataset mismatch(es) found`;
  });

  readonly naNote = computed(() => {
    const v = this.verdict();
    return v.rowLevelNa > 0
      ? `${v.rowLevelNa} formula/method combination(s) marked N/A -- documented limitation, not a failure (see REPORT.md)`
      : null;
  });
}
