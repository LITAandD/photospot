import type { SajuIn } from "@photospot/client";
export function formatBirthDate(value: string): string {
  const digits = value.replace(/[^0-9]/g, "").slice(0, 8);
  return [digits.slice(0, 4), digits.slice(4, 6), digits.slice(6, 8)].filter(Boolean).join("-");
}
export const BIRTH_HOURS: { id: NonNullable<SajuIn["birth_hour_branch"]>; label: string; range: string }[] = [
  { id: "zi", label: "자시", range: "23:00~01:00" }, { id: "chou", label: "축시", range: "01:00~03:00" },
  { id: "yin", label: "인시", range: "03:00~05:00" }, { id: "mao", label: "묘시", range: "05:00~07:00" },
  { id: "chen", label: "진시", range: "07:00~09:00" }, { id: "si", label: "사시", range: "09:00~11:00" },
  { id: "wu", label: "오시", range: "11:00~13:00" }, { id: "wei", label: "미시", range: "13:00~15:00" },
  { id: "shen", label: "신시", range: "15:00~17:00" }, { id: "you", label: "유시", range: "17:00~19:00" },
  { id: "xu", label: "술시", range: "19:00~21:00" }, { id: "hai", label: "해시", range: "21:00~23:00" },
];
