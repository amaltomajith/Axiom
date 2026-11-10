import { DOCUMENT, inject, InjectionToken } from '@angular/core';

const KEY = 'axiom_watch_visitor';
const VALID = /^[A-Za-z0-9-]{16,64}$/; // the backend's rule for X-Axiom-Visitor

/**
 * The anonymous id that scopes this browser's watchlist. It is an identifier, not authentication: anyone who
 * has it can edit that list. Storage can throw (private mode, blocked site data), so the id then lasts one visit.
 */
export function visitorId(storage: Storage | undefined, newId: () => string = () => crypto.randomUUID()): string {
  try {
    const saved = storage?.getItem(KEY);
    if (saved && VALID.test(saved)) return saved;
  } catch {
    /* storage unavailable */
  }
  const id = newId();
  try {
    storage?.setItem(KEY, id);
  } catch {
    /* storage unavailable: the id simply will not persist */
  }
  return id;
}

export const VISITOR_ID = new InjectionToken<string>('VISITOR_ID', {
  providedIn: 'root',
  factory: () => {
    let storage: Storage | undefined;
    try {
      storage = inject(DOCUMENT).defaultView?.localStorage;
    } catch {
      storage = undefined;
    }
    return visitorId(storage);
  },
});
