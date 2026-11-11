import '@testing-library/jest-dom';

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});

// jsdom has no ResizeObserver; Recharts' ResponsiveContainer needs one to mount.
if (typeof window.ResizeObserver === 'undefined') {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// Tests never touch the network: anything that calls fetch without injecting its own gets a refusal.
globalThis.fetch = (() => Promise.reject(new TypeError('network disabled in tests'))) as typeof fetch;

// jsdom has no canvas; return no context (the landing globe then draws nothing) instead of logging "not implemented".
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as typeof HTMLCanvasElement.prototype.getContext;

// jsdom has no IntersectionObserver; Motion's useInView and whileInView need one to mount.
if (typeof window.IntersectionObserver === 'undefined') {
  window.IntersectionObserver = class {
    readonly root = null;
    readonly rootMargin = '';
    readonly thresholds = [];
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  } as unknown as typeof IntersectionObserver;
}
