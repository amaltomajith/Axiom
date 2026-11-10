import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Store } from '@ngrx/store';
import { combineLatest, map, startWith } from 'rxjs';
import { PctPipe, PricePipe, RatingLabelPipe, RatingTonePipe } from '../core/format';
import { RunMonitorActions } from '../run/state/run.actions';
import { selectRunActive, selectRunTicker } from '../run/state/run.selectors';
import { WatchlistPageActions } from './state/watchlist.actions';
import { selectError, selectItems, selectLoaded, selectLoading, selectNotice, selectRatingsError, selectRows } from './state/watchlist.selectors';
import { SORT_OPTIONS, SortKey, visibleRows } from './view';

@Component({
  selector: 'app-watchlist',
  imports: [ReactiveFormsModule, PctPipe, PricePipe, RatingLabelPipe, RatingTonePipe],
  templateUrl: './watchlist.component.html',
  styleUrl: './watchlist.component.scss',
})
export class Watchlist {
  private readonly store = inject(Store);

  readonly filter = new FormControl('', { nonNullable: true });
  readonly sort = new FormControl<SortKey>('added', { nonNullable: true });
  readonly sortOptions = SORT_OPTIONS;

  /**
   * Derived view state: store rows combined with the two form controls. Any input changing recomputes the
   * visible rows; nothing is copied or synced by hand. startWith because valueChanges skips the initial value
   * and combineLatest waits for every input to emit once.
   */
  readonly rows = toSignal(
    combineLatest([
      this.store.select(selectRows),
      this.filter.valueChanges.pipe(startWith(this.filter.value)),
      this.sort.valueChanges.pipe(startWith(this.sort.value)),
    ]).pipe(map(([rows, filter, sort]) => visibleRows(rows, filter, sort))),
    { initialValue: [] },
  );

  readonly total = computed(() => this.items().length);
  private readonly items = this.store.selectSignal(selectItems);
  readonly loading = this.store.selectSignal(selectLoading);
  readonly loaded = this.store.selectSignal(selectLoaded);
  readonly error = this.store.selectSignal(selectError);
  readonly notice = this.store.selectSignal(selectNotice);
  readonly ratingsError = this.store.selectSignal(selectRatingsError);
  readonly runActive = this.store.selectSignal(selectRunActive);
  readonly runTicker = this.store.selectSignal(selectRunTicker);

  run(ticker: string): void {
    this.store.dispatch(RunMonitorActions.started({ ticker }));
  }

  remove(ticker: string): void {
    this.store.dispatch(WatchlistPageActions.removeRequested({ ticker }));
  }

  dismissNotice(): void {
    this.store.dispatch(WatchlistPageActions.noticeDismissed());
  }

  retryLoad(): void {
    this.store.dispatch(WatchlistPageActions.opened());
  }
}
