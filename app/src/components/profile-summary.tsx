import type { ProfileOut } from "@photospot/client";
import React from "react";
import { Body, Card, Muted } from "@/components/ui";
const GENDER: Record<string, string> = { female: "여성", male: "남성", other: "기타", undisclosed: "선택 안 함" };
const SEASON: Record<string, string> = { spring_warm: "봄 웜", summer_cool: "여름 쿨", autumn_warm: "가을 웜", winter_cool: "겨울 쿨" };
const TONE: Record<string, string> = { light: "라이트", bright: "브라이트", true: "트루", mute: "뮤트", deep: "딥" };
const BODY: Record<string, string> = { straight: "스트레이트", wave: "웨이브", natural: "내추럴" };
export function ProfileSummary({ profile: p }: { profile: ProfileOut }) {
  return <Card style={{ gap: 6 }}>
    <Body>내가 입력한 정보</Body>
    <Muted>성별 {GENDER[p.gender]} · 출생연도 {p.birth_year ? `${p.birth_year}년` : "미입력"} · 키 {p.height_cm ? `${p.height_cm}cm` : "미입력"}</Muted>
    <Muted>퍼스널컬러 {p.pc_season ? SEASON[p.pc_season] : "미입력"}{p.pc_subtone ? ` ${TONE[p.pc_subtone]}` : ""} · 체형 {p.body_type ? BODY[p.body_type] : "미입력"} · MBTI {p.mbti ?? "미입력"}</Muted>
    <Muted size={12}>퍼스널컬러 40점 · 체형 30점 · MBTI 30점. E/I는 2025년 입장객 순위, S/N은 공간 설명 문구, T/F는 건축·자연 공간을 비교해요. 키와 J/P는 배점에 반영하지 않아요. 부족한 오행·일진은 추가 추천에서 반영해요.</Muted>
  </Card>;
}
