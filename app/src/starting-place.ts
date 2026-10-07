import type { StartingPlace } from "./recommendation-regions";

export type Coordinates = { lat: number; lng: number };
export type StartingPlaceState = { place: StartingPlace | null; locating: boolean; note: string | null };
export const INITIAL_STARTING_PLACE: StartingPlaceState = { place: null, locating: true, note: null };

/** A manual choice always wins over an older, still-pending GPS lookup. */
export function createStartingPlace(
  lookup: () => Promise<Coordinates>,
  update: (state: StartingPlaceState) => void,
  timeoutMs = 12000,
) {
  let version = 0;
  let cancel: (() => void) | undefined;
  const invalidate = () => { version += 1; cancel?.(); cancel = undefined; };
  return {
    async locate() {
      invalidate();
      const request = version;
      update({ place: null, locating: true, note: null });
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        const position = await Promise.race([
          Promise.resolve().then(() => request === version ? lookup() : null),
          new Promise<null>((resolve, reject) => {
            cancel = () => resolve(null);
            timer = setTimeout(() => reject(new Error("현위치를 확인하지 못했어요. 아래에서 시작 장소를 선택해 주세요.")), timeoutMs);
          }),
        ]);
        if (request !== version || !position) return;
        const { lat, lng } = position;
        if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat < 33 || lat > 39 || lng < 124 || lng > 132) {
          throw new Error("현재는 국내 장소를 추천해요. 방문할 지역을 선택해 주세요.");
        }
        update({ place: { id: "current", label: "현위치", lat, lng }, locating: false, note: null });
      } catch (error) {
        if (request === version) update({ place: null, locating: false,
          note: error instanceof Error ? error.message : "현위치를 확인하지 못했어요. 시작 장소를 직접 선택해 주세요." });
      } finally {
        if (timer) clearTimeout(timer);
        if (request === version) cancel = undefined;
      }
    },
    select(place: StartingPlace) {
      invalidate();
      update({ place, locating: false, note: null });
    },
    dispose: invalidate,
  };
}
