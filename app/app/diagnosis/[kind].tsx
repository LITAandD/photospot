import { runDiagnosis, type DiagnosisKind, type DiagnosisOut } from "@photospot/client";
import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { api } from "@/api";
import { Body, Button, Card, ErrorBox, Label, Muted, Screen, Title } from "@/components/ui";
import { errorMessage, useAsync } from "@/hooks";
import { useOnboarding } from "@/state/onboarding";
import { colors, fonts } from "@/theme";

const KINDS: readonly DiagnosisKind[] = ["personal-color", "body-type"];
const isKind = (v: unknown): v is DiagnosisKind => typeof v === "string" && (KINDS as readonly string[]).includes(v);

export default function Diagnosis() {
  const { kind: param } = useLocalSearchParams<{ kind: string }>();
  const kind = isKind(param) ? param : null;
  const router = useRouter();
  const close = () => router.canGoBack() ? router.back() : router.replace('/onboarding/style');
  const { dispatch } = useOnboarding();
  const questions = useAsync(() => kind ? api.diagnosisQuestions(kind) : Promise.reject(new Error("알 수 없는 자가진단이에요")), [kind]);
  const [answers, setAnswers] = useState<number[]>([]);
  const [result, setResult] = useState<{ result: DiagnosisOut; patch: Record<string, unknown> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);                                       // 같은 프레임의 두 번 탭도 막는다
  const title = kind === "personal-color" ? "퍼스널컬러 자가진단" : kind === "body-type" ? "체형(골격) 자가진단" : "자가진단";

  const diagnose = async (all: number[]) => {
    if (!kind || sending.current) return;
    sending.current = true; setBusy(true); setError(null);
    try { setResult(await runDiagnosis(api, kind, all)); } catch (e) { setError(errorMessage(e)); }
    finally { sending.current = false; setBusy(false); }
  };
  const answer = (i: number) => {
    const total = questions.data?.length ?? 0;
    if (sending.current || !total || answers.length >= total) return;
    const next = [...answers, i];
    setAnswers(next);
    if (next.length === total) void diagnose(next);
  };
  // 문항을 못 불러왔으면 문항부터, 다 답했는데 진단이 실패했으면 같은 답으로 진단만 다시
  const retry = () => {
    if (questions.error || !questions.data) { setError(null); setAnswers([]); questions.reload(); return; }
    if (answers.length === questions.data.length) void diagnose(answers);
    else setError(null);
  };
  const apply = () => {
    if (result) dispatch({ type: "profile", patch: result.patch });
    close();
  };

  return (
    <Screen>
      <View style={s.header}>
        <Pressable onPress={close} accessibilityRole="button" accessibilityLabel="닫기" style={s.iconButton}><Text style={{ fontSize: 20 }}>×</Text></Pressable>
        <Label>{title}</Label>
      </View>
      {(questions.loading && !questions.data) || busy ? <ActivityIndicator color={colors.accent} /> : null}
      {questions.error || error ? <ErrorBox message={error ?? errorMessage(questions.error)} onRetry={kind ? retry : undefined} /> : null}
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
                <Pressable key={o} onPress={() => answer(i)} disabled={busy} accessibilityRole="button" accessibilityState={{ disabled: busy }} style={[s.option, busy && { opacity: 0.6 }]}><Body size={16}>{o}</Body></Pressable>
              ))}
            </View>
            <View style={{ flex: 1 }} />
            {answers.length > 0 ? <Button title="이전 질문" variant="outline" disabled={busy} onPress={() => { setError(null); setAnswers(answers.slice(0, -1)); }} /> : null}
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
          <Button title="다시 하기" variant="outline" onPress={() => { setAnswers([]); setResult(null); setError(null); }} />
        </View>
      ) : null}
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { height: 44, flexDirection: "row", alignItems: "center", gap: 8 },
  iconButton: { width: 44, height: 44, marginLeft: -10, alignItems: "center", justifyContent: "center" },
  seg: { flex: 1, height: 4, borderRadius: 2 },
  option: { minHeight: 58, paddingHorizontal: 18, justifyContent: "center", borderRadius: 14, borderWidth: 1.5, borderColor: colors.lineStrong, backgroundColor: colors.card },
});
