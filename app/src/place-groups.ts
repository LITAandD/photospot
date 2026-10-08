import type { PlaceGroup } from "@photospot/client";

export const PLACE_GROUPS: { value: PlaceGroup; label: string }[] = [
  { value: "all", label: "전체" }, { value: "cafe", label: "카페 및 식당" },
  { value: "travel", label: "여행 명소" }, { value: "festival", label: "축제·행사 공간" },
];
export const placeGroupLabel = (value: PlaceGroup) => PLACE_GROUPS.find((g) => g.value === value)!.label;
