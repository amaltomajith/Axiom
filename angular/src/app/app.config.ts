import { provideHttpClient, withFetch } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideEffects } from '@ngrx/effects';
import { provideState, provideStore } from '@ngrx/store';
import { routes } from './app.routes';
import { API_BASE } from './core/config';
import { devtools } from './devtools';
import * as runEffects from './run/state/run.effects';
import { runFeature } from './run/state/run.reducer';
import * as searchEffects from './search/state/search.effects';
import { searchFeature } from './search/state/search.reducer';
import * as watchlistEffects from './watchlist/state/watchlist.effects';
import { watchlistFeature } from './watchlist/state/watchlist.reducer';

export function appConfig(apiBase: string): ApplicationConfig {
  return {
    providers: [
      provideBrowserGlobalErrorListeners(),
      provideRouter(routes, withComponentInputBinding()),
      provideHttpClient(withFetch()),
      { provide: API_BASE, useValue: apiBase },
      provideStore(),
      provideState(watchlistFeature),
      provideState(searchFeature),
      provideState(runFeature),
      provideEffects(watchlistEffects, searchEffects, runEffects),
      ...devtools,
    ],
  };
}
