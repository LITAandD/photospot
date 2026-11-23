/** Preserve the complete image when the author does not permit modifications. */
export function photoAllowsModifications(photo?: { license?: string; license_url?: string | null } | null): boolean {
  if (!photo) return true;
  const label = photo.license ?? "";
  const url = photo.license_url ?? "";
  if (/by-(?:nc|nd)|변경\s*금지|내용\s*변경\s*불가|공공누리\s*제?\s*[234]\s*유형|type[_ ]?[234]/i.test(label)) return false;
  if (url) return /^https:\/\/creativecommons\.org\/(?:licenses\/by(?:-sa)?\/(?:1\.0|2\.0|2\.5|3\.0|4\.0)(?:\/[a-z]{2})?|publicdomain\/(?:zero|mark)\/1\.0)(?:\/deed\.[a-z-]+)?\/?$/i.test(url) ||
    url === "https://www.kogl.or.kr/info/licenseType1.do" || /^https:\/\/www\.gnu\.org\/licenses\/(?:old-licenses\/)?fdl(?:-1\.[123])?(?:\.html)?\/?$/.test(url);
  return /^CC BY(?:-SA)? (?:1\.0|2\.0|2\.5|3\.0|4\.0)(?: [A-Z]{2})?$/i.test(label);
}
