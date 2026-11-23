/** Calendar dates have no timezone; never convert through a local-time Date. */
export function formatVisitDate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const day = new Date(`${value}T12:00:00Z`);
  if (!Number.isFinite(day.getTime()) || day.toISOString().slice(0, 10) !== value) return value;
  const weekday = ['일', '월', '화', '수', '목', '금', '토'][day.getUTCDay()];
  return `${value.replace(/-/g, '.')} (${weekday})`;
}
