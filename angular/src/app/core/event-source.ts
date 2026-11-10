import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

export interface SseMessage {
  event: string;
  data: string;
}

/** The slice of the browser's EventSource this app uses, so tests can provide a fake. */
export interface EventSourceLike {
  readonly readyState: number;
  onerror: ((ev: Event) => unknown) | null;
  addEventListener(type: string, listener: (ev: MessageEvent) => void): void;
  removeEventListener(type: string, listener: (ev: MessageEvent) => void): void;
  close(): void;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

export const EVENT_SOURCE_FACTORY = new InjectionToken<EventSourceFactory>('EVENT_SOURCE_FACTORY', {
  providedIn: 'root',
  factory: () => (url: string) => new EventSource(url),
});

/** The connection failed or dropped. App-level refusals are SSE `error` events instead, never this. */
export class StreamTransportError extends Error {
  constructor(readonly readyState: number) {
    super('The run stream connection failed.');
    this.name = 'StreamTransportError';
  }
}

/**
 * A server-sent event stream as an Observable. Subscribing opens the connection; unsubscribing, completing or
 * erroring closes it, because the teardown below always runs. A transport error becomes an Observable error, so
 * the browser's built-in reconnect never fires: reconnecting is left to an explicit `retry`.
 */
export function fromEventSource(url: string, factory: EventSourceFactory, events: readonly string[]): Observable<SseMessage> {
  return new Observable<SseMessage>(subscriber => {
    const source = factory(url);
    const listeners = events.map(name => {
      const fn = (e: MessageEvent) => subscriber.next({ event: name, data: String(e.data) });
      source.addEventListener(name, fn);
      return [name, fn] as const;
    });
    source.onerror = () => subscriber.error(new StreamTransportError(source.readyState));
    return () => {
      for (const [name, fn] of listeners) source.removeEventListener(name, fn);
      source.onerror = null;
      source.close();
    };
  });
}
