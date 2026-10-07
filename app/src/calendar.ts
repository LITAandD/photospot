export function validCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function calendarMonth(year: number, month: number): (string | null)[] {
  const first = new Date(0);
  first.setUTCFullYear(year, month, 1);
  first.setUTCHours(12, 0, 0, 0);
  const next = new Date(first);
  next.setUTCMonth(month + 1, 0);
  const cells: (string | null)[] = Array(first.getUTCDay()).fill(null);
  for (let day = 1; day <= next.getUTCDate(); day++) {
    cells.push(`${String(year).padStart(4, '0')}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`);
  }
  while (cells.length % 7) cells.push(null);
  return cells;
}

export function moveCalendarMonth(year: number, month: number, delta: number) {
  const index = year * 12 + month + delta;
  return { year: Math.floor(index / 12), month: ((index % 12) + 12) % 12 };
}
