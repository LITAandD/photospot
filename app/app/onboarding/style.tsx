import { Link, useRouter } from "expo-router";
import React from "react";
import { View } from "react-native";

import { Button, Chip, Label, Muted, OptionRow, Screen, StepHeader, Title } from "@/components/ui";
import { useOnboarding } from "@/state/onboarding";
import { colors, fonts } from "@/theme";

const SEASONS = [
  { id: "spring_warm", name: "봄 웜", desc: "밝고 따뜻한", swatch: "#EFAE88" },
  { id: "summer_cool", name: "여름 쿨", desc: "밝고 부드러운", swatch: "#B3AFD8" },
  { id: "autumn_warm", name: "가을 웜", desc: "깊고 차분한", swatch: "#9A6A3C" },
  { id: "winter_cool", name: "겨울 쿨", desc: "선명하고 대비 큰", swatch: "#26314E" },
] as const;
const TONES = [["light", "라이트"], ["bright", "브라이트"], ["true", "트루"], ["mute", "뮤트"], ["deep", "딥"]] as const;
const BODIES = [
  { id: "straight", name: "스트레이트", desc: "직선적이고 탄탄한 실루엣" },
  { id: "wave", name: "웨이브", desc: "부드러운 곡선 실루엣" },
  { id: "natural", name: "내추럴", desc: "골격감 있는 자연스러운 실루엣" },
] as const;

const linkStyle = { fontFamily: fonts.body, fontSize: 13, color: colors.accent, textDecorationLine: "underline" as const };

export default function Style() {
  const router = useRouter();
  const { draft, dispatch } = useOnboarding();
  const p = draft.profile;
  return (
    <Screen>
      <StepHeader step={2} total={3} backHref="/onboarding/basic" skipHref="/onboarding/traits" />
      <View style={{ gap: 8 }}>
        <Label>2 / 3</Label>
        <Title>퍼스널컬러와 체형</Title>
        <Muted>빛과 배경의 조화를 고르는 참고 정보예요. 정답은 없으니 편하게 선택해 주세요.</Muted>
      </View>
      <View style={{ gap: 10 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" }}>
          <Label>퍼스널컬러</Label>
          <Link href="/diagnosis/personal-color" style={linkStyle}>자가진단 하기</Link>
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {SEASONS.map((sn) => (
            <View key={sn.id} style={{ width: "48%" }}>
              <OptionRow title={sn.name} desc={sn.desc} swatch={sn.swatch} selected={p.pc_season === sn.id}
                onPress={() => dispatch({ type: "profile", patch: { pc_season: p.pc_season === sn.id ? null : sn.id, pc_subtone: null } })} />
            </View>
          ))}
        </View>
      </View>
      {p.pc_season ? <View style={{ gap: 10 }}>
        <Label>세부 톤 <Muted>(선택)</Muted></Label>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {TONES.map(([id, label]) => (
            <Chip key={id} label={label} selected={p.pc_subtone === id}
              onPress={() => dispatch({ type: "profile", patch: { pc_subtone: p.pc_subtone === id ? null : id } })} />
          ))}
          <Chip label="잘 모르겠어요" selected={p.pc_subtone === null} onPress={() => dispatch({ type: "profile", patch: { pc_subtone: null } })} />
        </View>
      </View> : null}
      <View style={{ gap: 10 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" }}>
          <Label>체형 (골격)</Label>
          <Link href="/diagnosis/body-type" style={linkStyle}>자가진단 하기</Link>
        </View>
        {BODIES.map((b) => (
          <OptionRow key={b.id} title={b.name} desc={b.desc} selected={p.body_type === b.id}
            onPress={() => dispatch({ type: "profile", patch: { body_type: p.body_type === b.id ? null : b.id } })} />
        ))}
      </View>
      <View style={{ flex: 1 }} />
      <Button title="다음" onPress={() => router.push("/onboarding/traits")} />
    </Screen>
  );
}
