import * as Location from "expo-location";
import type { Coordinates } from "./starting-place";

export async function getCurrentLocation(): Promise<Coordinates> {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== "granted") throw new Error("위치 권한이 꺼져 있어요. 아래에서 시작 장소를 선택하거나 설정에서 위치 권한을 허용해 주세요.");
  const { coords } = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  return { lat: coords.latitude, lng: coords.longitude };
}
