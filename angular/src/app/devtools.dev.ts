import { EnvironmentProviders } from '@angular/core';
import { provideStoreDevtools } from '@ngrx/store-devtools';

/** Development only (swapped in by angular.json): Redux DevTools for the store. */
export const devtools: EnvironmentProviders[] = [provideStoreDevtools({ maxAge: 50, connectInZone: false })];
