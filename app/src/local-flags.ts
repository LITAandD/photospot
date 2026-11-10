import * as SecureStore from "expo-secure-store";

/** 기기에 남기는 동의·안내 플래그 (위치정보 동의, 베타 안내 닫기). 비밀값이 아니지만 앱에 설치된 유일한 영구 저장소가 SecureStore다 */
const key = (name: string) => `photospot.flag.${name}`;

export async function readFlag(name: string): Promise<boolean> {
  try { return (await SecureStore.getItemAsync(key(name))) === "1"; } catch { return false; }
}

export async function writeFlag(name: string, value: boolean): Promise<void> {
  try {
    if (value) await SecureStore.setItemAsync(key(name), "1");
    else await SecureStore.deleteItemAsync(key(name));
  } catch { /* 저장소를 쓸 수 없으면 이번 실행에서만 유지 */ }
}
