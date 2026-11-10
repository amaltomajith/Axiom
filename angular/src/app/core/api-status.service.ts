import { inject, Injectable } from '@angular/core';
import { catchError, defer, map, merge, Observable, of, retry, shareReplay, startWith, takeUntil, timeout, timer } from 'rxjs';
import { ApiService } from './api.service';
import { BACKOFF } from './backoff';
import { Health } from './models';

export type ApiStatus = 'checking' | 'waking' | 'ready' | 'unreachable';

/** How long a health check may take before the banner says the API is waking up. */
export const WAKE_HINT_MS = 2500;
const ATTEMPT_TIMEOUT_MS = 20_000;
const RETRIES = 5;

@Injectable({ providedIn: 'root' })
export class ApiStatusService {
  private readonly api = inject(ApiService);
  private readonly backoff = inject(BACKOFF);

  /**
   * Resolves once the API answers /api/health. Shared: the watchlist load, the ratings load and the banner all
   * wait on it, and that is one request, not three. `refCount: true` drops an in-flight check nobody waits
   * for any more; after an error the share resets, so the next subscriber starts a fresh check.
   */
  readonly ready$: Observable<Health> = defer(() => this.api.health()).pipe(
    timeout({ first: ATTEMPT_TIMEOUT_MS }),
    retry({ count: RETRIES, delay: (_err, attempt) => timer(this.backoff(attempt)) }),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  /** checking, then waking if the check is slow, then ready or unreachable. */
  readonly status$: Observable<ApiStatus> = this.statusOf(this.ready$);

  private statusOf(ready$: Observable<Health>): Observable<ApiStatus> {
    const settled$ = ready$.pipe(
      map((): ApiStatus => 'ready'),
      catchError(() => of<ApiStatus>('unreachable')),
    );
    const slow$ = timer(WAKE_HINT_MS).pipe(
      map((): ApiStatus => 'waking'),
      takeUntil(settled$),
    );
    return merge(settled$, slow$).pipe(startWith<ApiStatus>('checking'));
  }
}
