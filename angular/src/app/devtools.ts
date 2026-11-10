import { EnvironmentProviders } from '@angular/core';

/**
 * Production build: no store devtools. The development configuration in angular.json swaps this file for
 * devtools.dev.ts, so @ngrx/store-devtools never reaches the production bundle.
 */
export const devtools: EnvironmentProviders[] = [];
