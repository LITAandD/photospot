import type { Coordinates } from "./starting-place";

// Ask once through Geolocation itself; this also supports browsers without Permissions API.
export function getCurrentLocation(): Promise<Coordinates> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new Error("이 브라우저에서는 위치를 확인할 수 없어요. 시작 장소를 선택해 주세요."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => resolve({ lat: coords.latitude, lng: coords.longitude }),
      (error) => reject(new Error(error.code === 1
        ? "위치 권한이 꺼져 있어요. 아래에서 시작 장소를 선택하거나 브라우저의 위치 권한을 허용해 주세요."
        : "현위치를 확인하지 못했어요. 다시 시도하거나 시작 장소를 선택해 주세요.")),
      { enableHighAccuracy: false, maximumAge: 60000, timeout: 10000 },
    );
  });
}
