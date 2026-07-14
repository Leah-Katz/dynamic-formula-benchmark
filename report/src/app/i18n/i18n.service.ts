import { Injectable, computed, signal } from '@angular/core';
import { Locale, TRANSLATIONS } from './translations';

const STORAGE_KEY = 'dfeb-locale';

/**
 * Typed i18n service: active locale as a signal, EN/HE string maps, no
 * @angular/localize (which needs a locale-specific build/base-href and
 * would complicate the single-bundle GitHub Pages deploy). Persists the
 * choice to localStorage and reflects it onto <html dir/lang> so RTL and
 * the browser/assistive-tech language are always in sync with the UI.
 */
@Injectable({ providedIn: 'root' })
export class I18nService {
  private readonly _locale = signal<Locale>(this.initialLocale());

  readonly locale = this._locale.asReadonly();
  readonly dir = computed<'ltr' | 'rtl'>(() => (this._locale() === 'he' ? 'rtl' : 'ltr'));

  constructor() {
    this.applyToDocument(this._locale());
  }

  setLocale(locale: Locale): void {
    this._locale.set(locale);
    try {
      localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      /* localStorage unavailable (privacy mode etc.) -- locale still works for this session */
    }
    this.applyToDocument(locale);
  }

  /** Translates `key`, substituting any `{param}` tokens. Returns the key
   * itself if missing, so a gap is visible instead of silently blank. */
  t(key: string, params?: Record<string, string | number>): string {
    const text = TRANSLATIONS[this._locale()][key] ?? key;
    if (!params) return text;
    return Object.entries(params).reduce(
      (acc, [name, value]) => acc.replaceAll(`{${name}}`, String(value)),
      text,
    );
  }

  private initialLocale(): Locale {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === 'en' || stored === 'he') return stored;
    } catch {
      /* ignore */
    }
    return 'en';
  }

  private applyToDocument(locale: Locale): void {
    document.documentElement.setAttribute('dir', locale === 'he' ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', locale);
  }
}
