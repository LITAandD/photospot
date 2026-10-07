import { useRouter } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { Button, ErrorBox, Field, Label, Muted, OptionRow, Screen, StepHeader, Title } from "@/components/ui";
import { useOnboarding } from "@/state/onboarding";
import { DEMO } from "@/api";

const GENDERS = [["female", "여성"], ["male", "남성"], ["other", "기타"], ["undisclosed", "선택 안 함"]] as const;

export default function Basic() {
  const router = useRouter();
  const { draft, dispatch } = useOnboarding();
  const p = draft.profile;
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState(p.birth_year?.toString() ?? "");
  const [height, setHeight] = useState(p.height_cm?.toString() ?? "");
  const next = (skip = false) => {
    const birth = skip || !year.trim() ? null : Number(year);
    const cm = skip || !height.trim() ? null : Number(height);
    if (birth != null && (!Number.isInteger(birth) || birth < 1900 || birth > new Date().getFullYear())) return setError("출생연도를 확인해 주세요 (1900년~올해)");
    if (cm != null && (!Number.isFinite(cm) || cm < 100 || cm > 230)) return setError("키는 100~230cm 사이로 입력해 주세요");
    dispatch({ type: "profile", patch: { birth_year: birth, height_cm: cm } });
    router.push("/onboarding/style");
  };
  return (
    <Screen>
      <StepHeader step={1} total={3} backHref="/" onSkip={() => next(true)} />
      <View style={{ gap: 10 }}>
        <Label>1 / 3</Label>
        <Title>기본 정보를 알려주세요</Title>
        <Muted>{DEMO ? "키가 170cm보다 크면 야외, 작으면 실내 공간을 추천해요. 170cm는 중립이며 성별과 관계없이 같은 기준을 사용해요." : "키는 공간 크기와 촬영 구도를 추천할 때 써요. 성별은 키 구간을 나누는 기준이에요."}</Muted>
      </View>
      <View style={{ gap: 10 }}>
        <Label>성별</Label>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {GENDERS.map(([id, label]) => (
            <View key={id} style={{ width: "48%" }}>
              <OptionRow title={label} selected={p.gender === id} onPress={() => dispatch({ type: "profile", patch: { gender: id } })} />
            </View>
          ))}
        </View>
      </View>
      <Field label="출생연도" value={year} placeholder="예: 1998" keyboard="numeric" onChange={setYear} />
      <Field label="키" value={height} placeholder="예: 162" suffix="cm" keyboard="numeric" onChange={setHeight} />
      {error ? <ErrorBox message={error} /> : null}
      <View style={{ flex: 1 }} />
      <Button title="다음" onPress={() => next()} />
    </Screen>
  );
}
