export type FaceBox = { x: number; y: number; width: number; height: number };
export type VisitorPolicy = { enabled: boolean; version: string; operator: string; contact: string; policy_url: string; pending_days: number; public_days: number; max_file_bytes: number };
export type ExamplePhoto = { id: string; url: string; credit: string; caption: string; face_blurred: boolean };
export type Receipt = { id: string; state: 'pending' | 'approved' | 'rejected' | 'withdrawn'; note?: string; expires_at?: string };
export class VisitorPhotoError extends Error { constructor(message: string, readonly status: number) { super(message); } }

export function visitorBase() { return (process.env.EXPO_PUBLIC_PREVIEW_API_URL ?? '').replace(/\/$/, '') + '/preview/visitor-photos'; }
export async function visitorRequest<T>(path: string, body?: unknown, token?: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(visitorBase() + path, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'omit', signal,
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: 'Bearer ' + token } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new VisitorPhotoError(problem.title || '사진 요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.', response.status);
  }
  return response.json() as Promise<T>;
}
export const receiptState = (state: Receipt['state']) => ({ pending: '검수 대기', approved: '공개 중', rejected: '미채택', withdrawn: '철회 완료' }[state]);
export function parseReceipt(value: string): { id: string; token: string } | null {
  const match = /^([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.([0-9a-f]{64})$/i.exec(value.trim());
  return match ? { id: match[1].toLowerCase(), token: match[2].toLowerCase() } : null;
}
export function freshReceipt() {
  // Fail closed on insecure/unsupported browsers; never use Math.random for management tokens.
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return { id: crypto.randomUUID(), token: Array.from(bytes, n => n.toString(16).padStart(2, '0')).join('') };
}

