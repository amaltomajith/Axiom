import { HttpClient, HttpErrorResponse, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE } from './config';
import { Health, PriceSummary, ThesisRow, TickerMatch, WatchItem } from './models';
import { VISITOR_ID } from './visitor';

/** The only HttpClient user in the app. Effects call it; components never do. */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE);
  private readonly visitor = new HttpHeaders({ 'X-Axiom-Visitor': inject(VISITOR_ID) });

  health(): Observable<Health> {
    return this.http.get<Health>(`${this.base}/api/health`);
  }

  summary(ticker: string): Observable<PriceSummary> {
    return this.http.get<PriceSummary>(`${this.base}/api/quant/${encodeURIComponent(ticker)}/summary`);
  }

  /** Newest first, so the first row per ticker is its latest rating. */
  theses(limit = 200): Observable<ThesisRow[]> {
    return this.http.get<ThesisRow[]>(`${this.base}/api/theses`, { params: new HttpParams().set('limit', limit) });
  }

  searchTickers(q: string, limit = 8): Observable<TickerMatch[]> {
    return this.http.get<TickerMatch[]>(`${this.base}/api/tickers/search`, {
      params: new HttpParams().set('q', q).set('limit', limit),
    });
  }

  visitorWatchlist(): Observable<WatchItem[]> {
    return this.http.get<WatchItem[]>(`${this.base}/api/visitor/watchlist`, { headers: this.visitor });
  }

  watchAdd(ticker: string): Observable<WatchItem[]> {
    return this.http.put<WatchItem[]>(`${this.base}/api/visitor/watchlist/${encodeURIComponent(ticker)}`, null, {
      headers: this.visitor,
    });
  }

  watchRemove(ticker: string): Observable<WatchItem[]> {
    return this.http.delete<WatchItem[]>(`${this.base}/api/visitor/watchlist/${encodeURIComponent(ticker)}`, {
      headers: this.visitor,
    });
  }

  /** EventSource can only GET, so runs started here use the GET twin of POST /api/analyze. */
  runStreamUrl(ticker: string, equity = 100_000): string {
    return `${this.base}/api/analyze/stream?ticker=${encodeURIComponent(ticker)}&equity=${equity}`;
  }
}

/** A readable message for any API failure: the backend's `detail` or `error`, or a plain network message. */
export function apiErrorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0) return 'Cannot reach the Axiom API.';
    const body = err.error as { detail?: unknown; error?: unknown } | null;
    const msg = body?.detail ?? body?.error;
    if (typeof msg === 'string' && msg) return msg;
    return `The API answered ${err.status}.`;
  }
  if (err instanceof Error && err.name === 'TimeoutError') return 'The Axiom API took too long to answer.';
  return err instanceof Error ? err.message : 'Something went wrong.';
}
