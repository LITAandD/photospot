import { runDiagnosis, type DiagnosisKind, type DiagnosisOut } from "@photospot/client";
import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { api } from "@/api";
import { Body, Button, Card, ErrorBox, Label, Muted, Screen, Title } from "@/components/ui";
import { errorMessage, useAsync } from "@/hooks";
import { useOnboarding } from "@/state/onboarding";
import { colors, fonts } from "@/theme";

export default function Diagnosis() {
  const { kind } = useLocalSearchParams<{ kind: DiagnosisKind }>();
  const router = useRouter();
  const { dispatch } = useOnboarding();
  const questions = useAsync(() => api.diagnosisQuestions(kind), [kind]);
  const [answers, setAnswers] = useState<number[]>([]);
  const [result, setResult] = useState<{ result: DiagnosisOut; patch: Record<string, unknown> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const title = kind === "personal-color" ? "퍼스널컬러 자가진단" : "체형(골격) 자가진단";

  const answer = async (i: number) => {
    const next = [...answers, i];
    setAnswers(next);
    if (questions.data && next.length === questions.data.length) {
      try { setResult(await runDiagnosis(api, kind, next)); } catch (e) { setError(errorMessage(e)); }
    }
  };
  const apply = () => {
    if (result) dispatch({ type: "profile", patch: result.patch });
    router.back();
  };

  return (
    <Screen>
      <View style={s.header}>
        <Pressable onPress={() => router.back()} accessibilityLabel="닫기" style={s.iconButton}><Text style={{ fontSize: 20 }}>×</Text></Pressable>
        <Label>{title}</Label>
      </View>
      {questions.loading ? <ActivityIndicator color={colors.accent} /> : null}
      {questions.error || error ? <ErrorBox message={error ?? errorMessage(questions.error)} onRetry={questions.reload} /> : null}
      {questions.data && !result ? (() => {
        const step = Math.min(answers.length, questions.data.length - 1);
        const q = questions.data[step];
        return (
          <View style={{ flex: 1, gap: 24 }}>
            <View style={{ gap: 12 }}>
              <View style={{ flexDirection: "row", gap: 4 }}>
                {questions.data.map((_, i) => <View key={i} style={[s.seg, { backgroundColor: i <= step ? colors.accent : colors.line }]} />)}
              </View>
              <Label>질문 {step + 1} / {questions.data.length}</Label>
            </View>
            <Title size={26}>{q.text}</Title>
            <View style={{ gap: 10 }}>
              {q.options.map((o, i) => (
                <Pressable key={o} onPress={() => answer(i)} accessibilityRole="button" style={s.option}><Body size={16}>{o}</Body></Pressable>
              ))}
            </View>
            <View style={{ flex: 1 }} />
            {answers.length > 0 ? <Button title="이전 질문" variant="outline" onPress={() => setAnswers(answers.slice(0, -1))} /> : null}
          </View>
        );
      })() : null}
      {result ? (
        <View style={{ flex: 1, gap: 20 }}>
          <Card style={{ gap: 14, padding: 24 }}>
            <Label>진단 결과 · {{ high: "가능성 높음", medium: "가능성 보통", low: "판단이 애매해요" }[result.result.confidence]}</Label>
            <Title size={32}>{result.result.result_label}</Title>
            {result.result.second_label ? <Muted>다음 후보: {result.result.second_label}</Muted> : null}
          </Card>
          <Muted size={13}>{result.result.note}</Muted>
          <View style={{ flex: 1 }} />
          <Button title="이 결과로 입력하기" onPress={apply} />
          <Button title="다시 하기" variant="outline" onPress={() => { setAnswers([]); setResult(null); }} />
        </View>
      ) : null}
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { height: 44, flexDirection: "row", alignItems: "center", gap: 8 },
  iconButton: { width: 44, height: 44, marginLeft: -10, alignItems: "center", justifyContent: "center" },
  seg: { flex: 1, height: 4, borderRadius: 2 },
  option: { minHeight: 58, paddingHorizontal: 18, justifyContent: "center", borderRadius: 14, borderWidth: 1.5, borderColor: colors.line, backgroundColor: colors.card },
});
