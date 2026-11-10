import { DOCUMENT, inject, InjectionToken } from '@angular/core';
import { distinctUntilChanged, fromEvent, map, Observable, startWith } from 'rxjs';

/** True while the tab is visible. `visibilitychange` only fires on change, so start with the current state. */
export function pageVisible(doc: Document): Observable<boolean> {
  const visible = () => doc.visibilityState !== 'hidden';
  return fromEvent(doc, 'visibilitychange').pipe(map(visible), startWith(visible()), distinctUntilChanged());
}

/** Injected so effects can be marble-tested with a scripted visibility stream. */
export const PAGE_VISIBLE = new InjectionToken<Observable<boolean>>('PAGE_VISIBLE', {
  providedIn: 'root',
  factory: () => pageVisible(inject(DOCUMENT)),
});
