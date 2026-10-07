import React, { useState } from "react";
import { useRouter } from "expo-router";
import { Linking } from "react-native";
import { Body, Button, Card, ErrorBox, Muted, Screen, Title } from "@/components/ui";
import { DEMO } from "@/api";

export default function Privacy() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const open = (url: string) => Linking.openURL(url).catch(() => setError("문서를 열지 못했어요. 네트워크 연결을 확인해 주세요"));
  if (DEMO) return <Screen style={{ paddingTop: 24 }}>
    <Title>웹 체험 정보 처리 안내</Title>
    <Card><Body>이 브라우저에 보관해요</Body><Muted>프로필·계산된 오행 비율·저장 목록·후기·앱 의견은 이 브라우저에만 보관해요. 다른 기기와 동기화되지 않으며, 설정의 회원 탈퇴로 지울 수 있어요. 공용 기기에서는 체험 후 삭제해 주세요.</Muted></Card>
    <Card><Body>추천·사주 계산</Body><Muted>추천을 요청하면 선택한 프로필과 조회 위치·촬영일을 계산 서버로 보내요. 사주 계산에 동의하면 입력한 생년월일시를 보내요. 공개 웹 체험의 계산 서버는 Vercel에서 실행되며, 포토스팟은 계산 입력을 데이터베이스에 저장하지 않아요. 생년월일시와 사주 기둥은 브라우저에도 저장하지 않아요. 호스팅 제공자는 IP·접속 시각 등 운영 로그를 처리할 수 있어요.</Muted></Card>
    <Card><Body>위치와 사진</Body><Muted>추천 화면을 처음 열면 현위치 사용 권한을 요청해요. 허용하면 현위치 주변을 추천하고, 허용하지 않아도 도시와 주요 장소를 직접 골라 이용할 수 있어요. 위치를 계속 추적하지 않으며, 좌표를 프로필에 저장하지 않아요. 장소 사진은 표시된 외부 출처에서 불러와요. 개인 프로필을 사진·지도 제공자에게 보내지 않으며, 체험에서는 사진을 업로드하지 않아요.</Muted></Card>
    <Card><Body>체험 범위</Body><Muted>실제 소셜 로그인·SNS 연결·결제·광고 송출·GPT 분석은 실행하지 않아요. 작성한 의견도 운영자에게 전송되지 않고 이 브라우저에만 남아요. 추천과 MBTI·사주 결과는 취향 탐색을 위한 참고이며 사진 결과를 보장하지 않아요.</Muted></Card>
    <Button title="돌아가기" onPress={() => router.canGoBack() ? router.back() : router.replace("/")} />
  </Screen>;
  return <Screen style={{ paddingTop: 24 }}>
    <Title>개인정보 및 서비스 안내</Title>
    <Card><Body>선택한 프로필</Body><Muted>성별·출생연도·키·체형·퍼스널컬러·MBTI를 계정에 저장해요. 색과 빛, 공간의 형태·크기, 분위기를 맞추는 규칙 기반 추천이며 사진 결과를 보장하지 않아요. 출생연도는 현재 점수 계산에 사용하지 않아요.</Muted></Card>
    <Card><Body>사주 오행 · 선택</Body><Muted>동의하면 생년월일시로 오행을 계산해요. 서버는 원본과 사주 기둥을 저장하지 않고 오행 비율만 보관해요. MBTI·사주는 취향 탐색을 위한 참고 요소예요. 설정에서 오행을 삭제할 수 있어요.</Muted></Card>
    <Card><Body>위치 · 선택</Body><Muted>추천 화면을 처음 열면 현위치 사용 권한을 요청해요. 좌표는 주변 장소 조회에 사용하며 사용자 프로필에는 저장하지 않아요. 위치를 계속 추적하지 않으며, 권한 없이 도시와 주요 장소를 직접 골라도 이용할 수 있어요.</Muted></Card>
    <Card><Body>사진 · 선택</Body><Muted>동의한 사진만 분석해요. 서버는 GPS·기기 메타데이터를 제거하고 촬영 시각은 보관해요. 업로드 원본은 다른 사용자에게 공개하지 않아요. 분석 설정에 따라 외부 AI 서비스로 이미지가 전송될 수 있으므로 얼굴·개인정보 없는 사진을 선택해 주세요. 설정에서 사진을 삭제하고 동의를 철회할 수 있어요.</Muted></Card>
    <Card><Body>의견과 GPT 분석 · 선택</Body><Muted>의견과 선택한 분석 동의를 보관해요. AI 분석에 동의한 의견만 개발자가 개인정보를 검토·제거한 뒤 OpenAI API로 전송해요. 계정·프로필·위치 정보는 함께 전송하지 않아요. API 응답 저장은 끄지만 제공자의 보안상 보관 정책은 별도로 적용돼요. 의견 화면에서 삭제·동의 철회가 가능해요.</Muted></Card>
    <Card><Body>후원·구독·광고</Body><Muted>후원과 구독은 Apple·Google 스토어 및 RevenueCat으로 처리하며 계정 식별자와 구매 내역을 사용해요. 결제 카드 정보는 포토스팟에 저장하지 않아요. 광고는 검색 지역·공간 종류에 따라 표시하고 개인 체형·사주·MBTI를 광고주에게 보내지 않아요. 광고 불러오기·클릭은 계정별 하루 단위로 집계해요.</Muted></Card>
    <Card><Body>Instagram 연결</Body><Muted>본인 인증을 거친 계정 식별자·사용자명·연결 시각을 저장해요. 인증에 사용한 액세스 토큰은 보관하지 않아요. 사진·피드·메시지를 가져오거나 게시하지 않아요. 연결 해제 시 앱의 연결 정보가 삭제돼요.</Muted></Card>
    <Card><Body>계정 삭제</Body><Muted>설정의 회원 탈퇴로 프로필·오행·저장 목록·후기·업로드 사진·앱 의견·연결된 AI 개선안·SNS 연결 정보·앱의 구독 상태를 삭제해요. 이전 토큰 재사용을 막는 탈퇴 상태의 계정 식별자는 남아요. 스토어 구독은 별도로 취소해야 해요.</Muted></Card>
    {process.env.EXPO_PUBLIC_PRIVACY_URL ? <Button title="개인정보 처리방침 전문" variant="outline" onPress={() => open(process.env.EXPO_PUBLIC_PRIVACY_URL!)} /> : <Muted size={12}>현재는 개발 버전 안내예요. 정식 배포 전 운영자의 개인정보 처리방침을 연결해야 해요.</Muted>}
    {process.env.EXPO_PUBLIC_TERMS_URL ? <Button title="서비스 이용약관 전문" variant="outline" onPress={() => open(process.env.EXPO_PUBLIC_TERMS_URL!)} /> : null}
    {error ? <ErrorBox message={error} /> : null}
    <Button title="돌아가기" onPress={() => router.canGoBack() ? router.back() : router.replace("/")} />
  </Screen>;
}
