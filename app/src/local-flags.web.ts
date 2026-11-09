/** 브라우저에만 남기는 동의·안내 플래그. 저장소가 막혀 있으면 이번 탭에서만 유지한다 */
const memory = new Map<string, boolean>();
const key = (name: string) => `photospot.flag.${name}`;

export async function readFlag(name: string): Promise<boolean> {
  try { return localStorage.getItem(key(name)) === "1"; } catch { return memory.get(name) ?? false; }
}

export async function writeFlag(name: string, value: boolean): Promise<void> {
  memory.set(name, value);
  try {
    if (value) localStorage.setItem(key(name), "1");
    else localStorage.removeItem(key(name));
  } catch { /* 메모리에만 유지 */ }
}
