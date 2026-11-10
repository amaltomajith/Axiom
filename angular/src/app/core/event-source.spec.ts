import { Observable } from 'rxjs';
import { FakeEventSource } from '../../testing/fakes';
import { EventSourceFactory, fromEventSource, SseMessage, StreamTransportError } from './event-source';

function track(): { factory: EventSourceFactory; sources: FakeEventSource[] } {
  const sources: FakeEventSource[] = [];
  return { factory: url => (sources.push(new FakeEventSource(url)), sources[sources.length - 1]), sources };
}

/**
 * Positive control: the same wrapper WITHOUT a teardown. If the main test could not tell these two apart, it
 * would prove nothing.
 */
function fromEventSourceWithoutTeardown(url: string, factory: EventSourceFactory, events: string[]): Observable<SseMessage> {
  return new Observable<SseMessage>(subscriber => {
    const source = factory(url);
    for (const name of events) source.addEventListener(name, e => subscriber.next({ event: name, data: String(e.data) }));
    source.onerror = () => subscriber.error(new StreamTransportError(source.readyState));
  });
}

describe('fromEventSource', () => {
  it('opens lazily, one connection per subscription', () => {
    const { factory, sources } = track();
    const stream$ = fromEventSource('/s', factory, ['trace']);
    expect(sources.length).toBe(0);
    stream$.subscribe().unsubscribe();
    stream$.subscribe().unsubscribe();
    expect(sources.length).toBe(2);
  });

  it('closes the EventSource and removes its listeners on unsubscribe', () => {
    const { factory, sources } = track();
    const sub = fromEventSource('/s', factory, ['trace', 'result']).subscribe();
    expect(sources[0].closed).toBe(false);
    expect(sources[0].listenerCount()).toBe(2);

    sub.unsubscribe();

    expect(sources[0].closed).toBe(true);
    expect(sources[0].listenerCount()).toBe(0);
    expect(sources[0].onerror).toBeNull();
  });

  it('positive control: without the teardown the connection stays open after unsubscribe', () => {
    const { factory, sources } = track();
    const sub = fromEventSourceWithoutTeardown('/s', factory, ['trace', 'result']).subscribe();

    sub.unsubscribe();

    expect(sources[0].closed).toBe(false); // leaked: the socket would stay open
    expect(sources[0].listenerCount()).toBe(2);
  });

  it('forwards named events and closes when the subscriber completes the stream', () => {
    const { factory, sources } = track();
    const seen: SseMessage[] = [];
    const sub = fromEventSource('/s', factory, ['trace']).subscribe(m => {
      seen.push(m);
      sub?.unsubscribe();
    });
    sources[0].emit('trace', '{"seq":1}');
    sources[0].emit('ignored', 'x');
    expect(seen).toEqual([{ event: 'trace', data: '{"seq":1}' }]);
    expect(sources[0].closed).toBe(true);
  });

  it('turns a transport error into an Observable error and closes, so the browser cannot auto-reconnect', () => {
    const { factory, sources } = track();
    let error: unknown;
    fromEventSource('/s', factory, ['trace']).subscribe({ error: e => (error = e) });
    sources[0].fail();
    expect(error).toBeInstanceOf(StreamTransportError);
    expect(sources[0].closed).toBe(true);
  });
});
