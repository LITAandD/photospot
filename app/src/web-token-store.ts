import type { TokenStore } from "@photospot/client";

/** Real credentials live only in memory. Preview tokens are public placeholders. */
export function createWebTokenStore(demo = false): TokenStore {
  const key = "photospot.demo.tokens";
  let memory: { access: string; refresh: string } | null = null;
  // Remove credentials persisted by older builds, including when running the preview.
  try { localStorage.removeItem("photospot.tokens"); } catch { /* SSR or blocked storage */ }
  return {
    get() {
      if (!demo) return memory;
      try {
        const value: unknown = JSON.parse(localStorage.getItem(key) ?? "null");
        if (value && typeof value === "object" && "access" in value && "refresh" in value
          && value.access === "personal-preview-access" && value.refresh === "personal-preview-refresh") {
          return { access: value.access, refresh: value.refresh };
        }
      } catch { /* Use this tab's memory when storage is unavailable. */ }
      return memory;
    },
    set(tokens) {
      memory = tokens;
      if (demo && tokens.access === "personal-preview-access" && tokens.refresh === "personal-preview-refresh") {
        try { localStorage.setItem(key, JSON.stringify(tokens)); } catch { /* memory only */ }
      }
    },
    clear() {
      memory = null;
      try { localStorage.removeItem(key); localStorage.removeItem("photospot.tokens"); } catch { /* already inaccessible */ }
    },
  };
}
