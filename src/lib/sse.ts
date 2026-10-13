// Minimal Server-Sent Events parser for fetch() streams (EventSource cannot POST or send headers).

export interface SseMessage {
  event: string;
  data: string;
}

/** Incremental parser: feed it decoded text chunks, it returns the complete messages seen so far. */
export class SseParser {
  private buffer = '';
  private event = 'message';
  private data: string[] = [];

  push(chunk: string): SseMessage[] {
    this.buffer += chunk;
    const out: SseMessage[] = [];
    let idx: number;
    while ((idx = this.buffer.search(/\r\n|\n|\r/)) !== -1) {
      const line = this.buffer.slice(0, idx);
      const sep = this.buffer.slice(idx).match(/^(\r\n|\n|\r)/)![0];
      // A lone "\r" at the very end may be the first half of "\r\n": wait for more input.
      if (sep === '\r' && idx + 1 === this.buffer.length) break;
      this.buffer = this.buffer.slice(idx + sep.length);

      if (line === '') {
        if (this.data.length) out.push({ event: this.event, data: this.data.join('\n') });
        this.event = 'message';
        this.data = [];
      } else if (line.startsWith(':')) {
        // comment / keep-alive ping
      } else {
        const colon = line.indexOf(':');
        const field = colon === -1 ? line : line.slice(0, colon);
        let value = colon === -1 ? '' : line.slice(colon + 1);
        if (value.startsWith(' ')) value = value.slice(1);
        if (field === 'event') this.event = value;
        else if (field === 'data') this.data.push(value);
      }
    }
    return out;
  }
}

export interface StreamOptions {
  url: string;
  body: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  onMessage: (msg: SseMessage) => void;
  fetchImpl?: typeof fetch;
}

/** POST and stream SSE messages to `onMessage`. Rejects on a non-2xx response (message from JSON body). */
export async function streamSse({ url, body, headers, signal, onMessage, fetchImpl = fetch }: StreamOptions): Promise<void> {
  const res = await fetchImpl(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...headers },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = j.error ?? j.detail ?? msg;
    } catch {
      /* ignore */
    }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const m of parser.push(decoder.decode(value, { stream: true }))) onMessage(m);
  }
}
