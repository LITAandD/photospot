/** Search by the displayed place name, including its branch, without an address. */
export function naverMapUrl(placeName?: string | null, verifiedUrl?: string | null): string | null {
  const query = placeName?.trim().replace(/\s+/g, " ");
  if (query) return `https://map.naver.com/p/search/${encodeURIComponent(query)}`;
  if (!verifiedUrl) return null;
  try {
    const url = new URL(verifiedUrl);
    if (url.protocol !== "https:" || url.username || url.password || url.port) return null;
    // When a name is unavailable, an exact verified place page is still usable.
    if (url.hostname === "map.naver.com" && /^\/p\/entry\/place\/\d+\/?$/.test(url.pathname)) return url.origin + url.pathname;
    if (["m.place.naver.com", "pcmap.place.naver.com"].includes(url.hostname) && /^\/(restaurant|place|cafe)\/\d+(\/home)?\/?$/.test(url.pathname)) return url.origin + url.pathname;
  } catch { /* An invalid or legacy search link is not a usable destination. */ }
  return null;
}

/** Public Maps search URL; no API key or device location is sent. */
export function googleMapUrl(placeName?: string | null): string | null {
  const query = placeName?.trim().replace(/\s+/g, " ");
  return query ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}` : null;
}
