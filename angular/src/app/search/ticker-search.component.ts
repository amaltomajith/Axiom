import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Store } from '@ngrx/store';
import { TickerMatch } from '../core/models';
import { WatchlistPageActions } from '../watchlist/state/watchlist.actions';
import { selectWatchedSet } from '../watchlist/state/watchlist.selectors';
import { TickerSearchActions } from './state/search.actions';
import { searchFeature } from './state/search.reducer';

/** Search-as-you-type combobox. Typing only dispatches; the debounce, cancellation and HTTP live in search.effects.ts. */
@Component({
  selector: 'app-ticker-search',
  imports: [ReactiveFormsModule],
  templateUrl: './ticker-search.component.html',
  styleUrl: './ticker-search.component.scss',
})
export class TickerSearch {
  private readonly store = inject(Store);

  readonly query = new FormControl('', { nonNullable: true });
  readonly results = this.store.selectSignal(searchFeature.selectResults);
  readonly pending = this.store.selectSignal(searchFeature.selectPending);
  readonly error = this.store.selectSignal(searchFeature.selectError);
  readonly answered = this.store.selectSignal(searchFeature.selectAnswered);
  readonly current = this.store.selectSignal(searchFeature.selectQuery);
  readonly watched = this.store.selectSignal(selectWatchedSet);

  readonly open = signal(false);
  readonly active = signal(-1);

  readonly showList = computed(() => this.open() && this.current().trim() !== '' && this.results().length > 0);
  readonly statusText = computed(() => {
    const q = this.current().trim();
    if (!q) return '';
    if (this.pending()) return 'Searching';
    if (this.error()) return this.error() ?? '';
    if (this.answered() === q && this.results().length === 0) return 'No ticker with SEC filings matches that.';
    const n = this.results().length;
    return `${n} match${n === 1 ? '' : 'es'}`;
  });

  constructor() {
    this.query.valueChanges.pipe(takeUntilDestroyed()).subscribe(query => {
      this.open.set(true);
      this.active.set(-1);
      this.store.dispatch(TickerSearchActions.queryChanged({ query }));
    });
  }

  pick(match: TickerMatch): void {
    if (this.watched().has(match.ticker)) return;
    this.store.dispatch(WatchlistPageActions.addRequested({ ticker: match.ticker, requestedAt: Date.now() / 1000 }));
    this.query.setValue('');
    this.open.set(false);
  }

  onKeydown(e: KeyboardEvent): void {
    const n = this.results().length;
    if (e.key === 'ArrowDown' && n) {
      e.preventDefault();
      this.open.set(true);
      this.active.set((this.active() + 1) % n);
    } else if (e.key === 'ArrowUp' && n) {
      e.preventDefault();
      this.active.set(this.active() <= 0 ? n - 1 : this.active() - 1);
    } else if (e.key === 'Enter' && this.showList()) {
      e.preventDefault();
      this.pick(this.results()[Math.max(0, this.active())]);
    } else if (e.key === 'Escape') {
      this.open.set(false);
      this.active.set(-1);
    }
  }
}
