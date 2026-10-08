/** Preserve the complete image when the author does not permit modifications. */
export function photoAllowsModifications(photo?: { license?: string; license_url?: string | null } | null): boolean {
  return !(/\bby-nd\b|\bby-nc-nd\b|변경\s*금지|내용\s*변경\s*불가|공공누리\s*[34]\s*유형/i.test(photo?.license ?? "") ||
    /creativecommons\.org\/licenses\/by(?:-nc)?-nd\//i.test(photo?.license_url ?? ""));
}
