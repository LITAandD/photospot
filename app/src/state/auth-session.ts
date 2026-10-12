import type { TokenStore } from '@photospot/client';

const listeners = new Set<(signedIn: boolean) => void>();
export const onSessionChange = (listener: (signedIn: boolean) => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};

/** Notify the root gate after storage succeeds. No credentials in events. */
export function observableTokens(store: TokenStore): TokenStore {
  return {
    get: () => store.get(),
    async set(tokens) { await store.set(tokens); listeners.forEach(fn => fn(true)); },
    async clear() { await store.clear(); listeners.forEach(fn => fn(false)); },
  };
}
