import fixtures from "./fixtures.json";
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
const problem = (status: number, title: string) => new Response(JSON.stringify({ status, title }), { status });
const PC = fixtures.diagnosis_questions["personal-color"];
const PC_AXIS = ["w", "w", "w", "d", "d", "d"];
const PC_SCORE: number[][] = [[1, -1, 0], [1, -1, 0], [1, -1, 0], [-1, 1, 0], [-1, 1, 0], [-1, 1, 0]];
const SEASON_LABEL: Record<string, string> = { spring_warm: "봄 웜", summer_cool: "여름 쿨", autumn_warm: "가을 웜", winter_cool: "겨울 쿨" };
const BODY_LABEL: Record<string, string> = { straight: "스트레이트", wave: "웨이브", natural: "내추럴" };
const seasonOf = (w: number, d: number) => (w > 0 ? (d > 0 ? "autumn_warm" : "spring_warm") : d > 0 ? "winter_cool" : "summer_cool");

export function diagnose(kind: string, answers: number[]) {
  if (kind === "personal-color") {
    if (answers.length !== PC.length) return problem(422, `답변은 ${PC.length}개여야 해요`);
    let w = 0, d = 0;
    answers.forEach((a, i) => { if (PC_AXIS[i] === "w") w += PC_SCORE[i][a]; else d += PC_SCORE[i][a]; });
    const result = seasonOf(w, d);
    const second = Math.abs(w) <= Math.abs(d) ? seasonOf(w > 0 ? -1 : 1, d) : seasonOf(w, d > 0 ? -1 : 1);
    const strength = Math.abs(w) + Math.abs(d);
    return json({ result, result_label: SEASON_LABEL[result], confidence: strength >= 4 ? "high" : strength >= 2 ? "medium" : "low",
      second, second_label: SEASON_LABEL[second], note: "자가진단은 참고용이에요. 정확하게 알고 싶다면 드레이핑 진단을 받아보세요." });
  }
  if (answers.length !== 5) return problem(422, "답변은 5개여야 해요");
  const keys = ["straight", "wave", "natural"];
  const counts = [0, 0, 0];
  answers.forEach((a) => { counts[a] += 1; });
  const order = [0, 1, 2].sort((a, b) => counts[b] - counts[a] || a - b);
  const top = keys[order[0]], runner = keys[order[1]];
  return json({ result: top, result_label: BODY_LABEL[top],
    confidence: counts[order[0]] >= 4 ? "high" : counts[order[0]] > counts[order[1]] ? "medium" : "low",
    second: counts[order[1]] > 0 ? runner : null, second_label: counts[order[1]] > 0 ? BODY_LABEL[runner] : null,
    note: "자가진단은 참고용이에요. 결과는 언제든 바꿀 수 있어요." });
}

