import type { Href } from 'expo-router';
import { ALL_AREAS } from './recommendation-regions';
import { clearIntendedRoute, peekIntendedRoute, rememberIntendedRoute } from './state/auth-session';

const AREA_IDS = { seoul: 'seoul-jongno', busan: 'busan-haeundae', gangneung: 'gangneung-gyeongpo', jeju: 'jeju-city' } as const;
export type BrowseCity = keyof typeof AREA_IDS;
export type BrowseContext = { city: BrowseCity; date: string; place?: string };
export const browseArea = (city: BrowseCity) => ALL_AREAS.find(area => area.id === AREA_IDS[city])!;
export function browseDate(value: unknown, fallback: string): string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return fallback;
  const parsed = new Date(value + 'T12:00:00Z');
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : fallback;
}
export function browseContext(params: Record<string, unknown>, fallback: string): BrowseContext | null {
  if (typeof params.city !== 'string' || !Object.hasOwn(AREA_IDS, params.city)) return null;
  const place = typeof params.place === 'string' && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(params.place) ? params.place : undefined;
  return { city: params.city as BrowseCity, date: browseDate(params.date, fallback), ...(place ? { place } : {}) };
}
export function browseHref(context: BrowseContext, detail = true): Href {
  return { pathname: detail && context.place ? '/browse/[id]' : '/browse',
    params: { city: context.city, date: context.date, ...(detail && context.place ? { id: context.place } : {}) } } as Href;
}
export const browseHomeHref = (c: BrowseContext) => `/home?city=${c.city}&date=${c.date}${c.place ? `&place=${encodeURIComponent(c.place)}` : ''}`;

// Only public navigation choices; no profile or consent. Tab-local, expires after two hours.
const KEY = 'photospot.browse.customization';
let pending: { context: BrowseContext; at: number } | null = null;
export function beginBrowseCustomization(context: BrowseContext) {
  pending = { context, at: Date.now() };
  try { sessionStorage.setItem(KEY, JSON.stringify(pending)); } catch { /* memory only */ }
  rememberIntendedRoute(browseHomeHref(context));
}
export function pendingBrowse(): BrowseContext | null {
  let value = pending;
  try { if (!value) value = JSON.parse(sessionStorage.getItem(KEY) ?? 'null'); } catch { /* memory only */ }
  if (!value || !Number.isFinite(value.at) || Date.now() - value.at > 2 * 60 * 60 * 1000 || value.at > Date.now()) return null;
  if (!value.context || typeof value.context !== 'object') return null;
  const context = browseContext(value.context, '');
  return context?.date ? context : null;
}
export function clearBrowseCustomization(cancel = false) {
  const context = pendingBrowse();
  if (cancel && context && peekIntendedRoute() === browseHomeHref(context)) clearIntendedRoute();
  pending = null;
  try { sessionStorage.removeItem(KEY); } catch { /* memory only */ }
}
