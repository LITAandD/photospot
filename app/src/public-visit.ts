import type { PublicPlace } from './public-browse';

type Hours = PublicPlace['hours'];
// Only an unambiguous, single, same-day interval is suitable for a compact clock.
const INTERVAL = /^(?:[월화수목금토일]\s+)?((?:[01]\d|2[0-3]):[0-5]\d)[–~−-]((?:[01]\d|2[0-3]):[0-5]\d)(?:\s+\((?:정규|특별 일정|공식 날짜별)\))?$/;
const minutes = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
const clock = (value: number) => `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;

export function visitHours(hours: Hours) {
  if (!hours || hours.stale || hours.schedule_kind === 'source_text') {
    return { status: 'unknown', title: '운영시간 확인 필요', cutoff: null } as const;
  }
  if (hours.closed) return { status: 'closed', title: '선택일 휴관·휴무', cutoff: null } as const;
  const interval = INTERVAL.exec(hours.summary.trim());
  if (!interval || minutes(interval[2]) <= minutes(interval[1])) {
    // Keep verified overnight/24h/split schedules readable, but do not infer a deadline.
    const unknown = /확인 필요|공식 안내 확인/.test(hours.summary);
    return { status: unknown ? 'unknown' : 'guidance', title: hours.summary.replace(/^[월화수목금토일]\s+/, ''), cutoff: null } as const;
  }
  let cutoff: string | null = null;
  if (hours.provider === 'official' && hours.source_url && hours.checked_at) {
    const candidates = hours.notes.filter(note => /입장\s*마감/.test(note));
    // Conditional or conflicting instructions remain in details, not an inferred deadline.
    if (candidates.length === 1) {
      const explicit = /^입장\s*마감(?:은)?\s*((?:[01]\d|2[0-3]):[0-5]\d)[.]?$/.exec(candidates[0]);
      const relative = /^입장\s*마감(?:은)? 관람 종료 (\d{1,2})시간 전[.]?$/.exec(candidates[0]);
      const value = explicit ? minutes(explicit[1]) : relative ? minutes(interval[2]) - Number(relative[1]) * 60 : null;
      if (value !== null && value >= minutes(interval[1]) && value <= minutes(interval[2])) cutoff = clock(value);
    }
  }
  return { status: 'hours', title: `${interval[1]}–${interval[2]}`, cutoff } as const;
}

/** A compact lead, always accompanied by the full admission text in the disclosure. */
export function admissionLead(value: string) {
  const lead = value.split(/\s+[（(]/, 1)[0].trim();
  return lead.length && lead.length <= 40 ? lead : value;
}
