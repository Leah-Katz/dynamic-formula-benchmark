import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { I18nService } from '../../i18n/i18n.service';
import { FormulaCategory, FormulaResult } from '../../models/benchmark.model';

/**
 * Renders the full formula catalog (all 13 rows straight from t_targil,
 * via export_report.py -- never hardcoded here). Charts that label their
 * x-axis with #targil_id are cross-referable to this table's "#" column.
 */
@Component({
  selector: 'app-formula-catalog',
  standalone: true,
  templateUrl: './formula-catalog.html',
  styleUrl: './formula-catalog.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FormulaCatalogComponent {
  protected readonly i18n = inject(I18nService);
  readonly formulas = input.required<FormulaResult[]>();

  categoryLabel(category: FormulaCategory): string {
    return this.i18n.t(`category.${category}`);
  }
}
