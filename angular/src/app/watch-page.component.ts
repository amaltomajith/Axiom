import { Component, inject, input, OnInit } from '@angular/core';
import { Store } from '@ngrx/store';
import { RunMonitor } from './run/run-monitor.component';
import { TickerSearch } from './search/ticker-search.component';
import { WatchlistPageActions } from './watchlist/state/watchlist.actions';
import { Watchlist } from './watchlist/watchlist.component';

@Component({
  selector: 'app-watch-page',
  imports: [TickerSearch, Watchlist, RunMonitor],
  template: `
    <h1 class="visually-hidden">Axiom Watch</h1>
    <div class="layout">
      <section class="col" aria-labelledby="watchlist-heading">
        <app-ticker-search />
        <app-watchlist />
      </section>
      <aside class="col" aria-labelledby="run-heading">
        <app-run-monitor [ticker]="ticker()" />
      </aside>
    </div>
  `,
  styles: `
    .layout {
      display: grid;
      gap: 1.25rem;
      grid-template-columns: minmax(0, 1fr);
    }
    .col {
      display: flex;
      flex-direction: column;
      gap: 1rem;
      min-width: 0;
    }
    @media (min-width: 64rem) {
      .layout {
        grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
        align-items: start;
      }
    }
  `,
})
export class WatchPage implements OnInit {
  /** bound from the `run/:ticker` route parameter */
  readonly ticker = input<string>();
  private readonly store = inject(Store);

  ngOnInit(): void {
    this.store.dispatch(WatchlistPageActions.opened());
  }
}
