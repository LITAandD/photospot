import { PUBLIC_WEB_URL } from './share';
import { browseContext, browseDate } from './browse-context';

/** Search engines get city-specific canonical URLs; shares retain the visit date. */
export function buildPublicUrls(pathname: string, params: { city?: unknown; date?: unknown }) {
  const url = new URL(pathname, PUBLIC_WEB_URL);
  const context = pathname === '/browse' || pathname.startsWith('/browse/') ? browseContext({ city: params.city }, '') : null;
  if (context) url.searchParams.set('city', context.city);
  const canonical = url.href;
  const date = browseDate(params.date, '');
  if (context && date) url.searchParams.set('date', date);
  return { canonical, share: url.href };
}
