import type { RecommendationItem } from '@photospot/client';

/** Only evaluated, positive evidence may become a recommendation reason. */
export function recommendationSummary(item: RecommendationItem) {
  const scoring = item.scoring;
  const metrics = scoring?.metrics ?? [];
  const evaluated = metrics.filter(m => m.status === 'scored');
  const positive = evaluated.filter(m => (m.points ?? 0) > 0)
    .sort((a, b) => (b.points ?? 0) - (a.points ?? 0))[0];
  const reason = positive ? `${positive.label} · 입력한 취향과 잘 맞아요`
    : evaluated.length ? '확인된 조건을 비교했어요. 상세 근거를 살펴보세요'
    : '선택한 지역에서 둘러볼 수 있는 장소예요';
  const photo = scoring?.photo_analysis_pending ? '사진 분석 대기'
    : scoring?.basis === 'photo' ? (evaluated.length ? '사진 분석 반영' : '사진 분석 자료 있음') : '사진 분석 미반영';
  return { reason, evidence: `평가 ${evaluated.length}/${metrics.length}항목 · ${photo}` };
}
