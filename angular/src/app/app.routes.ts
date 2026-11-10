import { Routes } from '@angular/router';
import { WatchPage } from './watch-page.component';

export const routes: Routes = [
  { path: '', component: WatchPage, title: 'Axiom Watch' },
  // a deep link, so the nginx and Vercel SPA fallback has something real to serve
  { path: 'run/:ticker', component: WatchPage, title: 'Axiom Watch: run' },
  { path: '**', redirectTo: '' },
];
