import type { ProfileOut } from "@photospot/client";
import React from "react";
import { Body, Card, Muted } from "@/components/ui";
import { DEMO } from "@/api";
const GENDER: Record<string, string> = { female: "여성", male: "남성", other: "기타", undisclosed: "선택 안 함" };
const SEASON: Record<string, string> = { spring_warm: "봄 웜", summer_cool: "여름 쿨", autumn_warm: "가을 웜", winter_cool: "겨울 쿨" };
const TONE: Record<string, string> = { light: "라이트", bright: "브라이트", true: "트루", mute: "뮤트", deep: "딥" };
const BODY: Record<string, string> = { straight: "스트레이트", wave: "웨이브", natural: "내추럴" };
export function ProfileSummary({ profile: p }: { profile: ProfileOut }) {
  return <Card style={{ gap: 6 }}>
    <Body>내가 입력한 정보</Body>
    <Muted>성별 {GENDER[p.gender]} · 출생연도 {p.birth_year ? `${p.birth_year}년` : "미입력"} · 키 {p.height_cm ? `${p.height_cm}cm` : "미입력"}</Muted>
    <Muted>퍼스널컬러 {p.pc_season ? SEASON[p.pc_season] : "미입력"}{p.pc_subtone ? ` ${TONE[p.pc_subtone]}` : ""} · 체형 {p.body_type ? BODY[p.body_type] : "미입력"} · MBTI {p.mbti ?? "미입력"}</Muted>
    <Muted size={12}>{DEMO ? "체형은 사진의 곡선·직선·큰 형체, 퍼스널컬러는 사진 색조, 키는 170cm 기준 실내외 공간과 비교해요. MBTI E/I는 최근 3개월 방문객 순위를 사용하며 미집계 항목은 제외해요. 부족한 오행·일진은 추가 추천 탭에서 반영해요." : "키·체형·퍼스널컬러와 MBTI의 E/I·S/N·T/F를 기본 추천에 사용해요. 부족한 오행·일진은 추가 선택한 탭에서만 반영해요. 성별은 키 구간에, 출생연도와 J/P는 프로필 표시에 사용해요."}</Muted>
  </Card>;
}
