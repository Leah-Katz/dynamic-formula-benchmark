import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { I18nService } from '../../i18n/i18n.service';
import { ComparisonVerdict } from '../../models/benchmark.model';

@Component({
  selector: 'app-correctness-badge',
  standalone: true,
  templateUrl: './correctness-badge.html',
  styleUrl: './correctness-badge.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CorrectnessBadgeComponent {
  protected readonly i18n = inject(I18nService);
  readonly verdict = input.required<ComparisonVerdict>();

  readonly statusLabel = computed(() => this.i18n.t(this.verdict().allPass ? 'badge.allAgree' : 'badge.mismatch'));

  readonly detail = computed(() => {
    const v = this.verdict();
    return v.allPass
      ? this.i18n.t('badge.detailPass', { tolerance: v.tolerance.toExponential(0) })
      : this.i18n.t('badge.detailFail', { rowFail: v.rowLevelFail, fullFail: v.fullDatasetFail });
  });

  // Echoes the coverage-callout's finding (see coverage-callout.ts) and
  // links to it -- an N/A here IS that finding, not a separate caveat.
  readonly naNote = computed(() => {
    const v = this.verdict();
    return v.rowLevelNa > 0 ? this.i18n.t('badge.naNote', { count: v.rowLevelNa }) : null;
  });
}
