import { ApiError } from "@photospot/client";
import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/**
 * 로딩·오류·재시도를 한 번에 다루는 작은 훅.
 * 같은 조건의 reload/refreshKey 변경에만 이전 data를 유지한다.
 * deps가 바뀌면 이전 조건의 결과·오류는 즉시 숨겨 다른 지역/날짜의 결과로 보이지 않게 한다.
 * 첫 로딩 표시는 `loading && !data`로 판단한다.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], refreshKey?: unknown) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const key = useMemo(() => ({}), deps);
  const [state, setState] = useState<{ key: object; data: T | null; error: ApiError | Error | null; loading: boolean }>(
    { key, data: null, error: null, loading: true });
  const generation = useRef(0);
  const run = useCallback(() => {
    const current = ++generation.current;
    setState((prev) => ({ key, data: prev.key === key ? prev.data : null, error: null, loading: true }));
    Promise.resolve().then(fn)
      .then((data) => { if (current === generation.current) setState({ key, data, error: null, loading: false }); })
      .catch((error) => { if (current === generation.current) setState((prev) => ({ ...prev, error, loading: false })); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, refreshKey]);
  useEffect(() => { run(); return () => { generation.current += 1; }; }, [run]);
  return { data: state.key === key ? state.data : null, error: state.key === key ? state.error : null,
    loading: state.key !== key || state.loading, reload: run };
}

/** 화면에 다시 돌아왔을 때만 실행 (처음 마운트 때의 포커스는 건너뛰어 중복 요청을 막는다) */
export function useRefocus(fn: () => void) {
  const latest = useRef(fn);
  latest.current = fn;
  const mounted = useRef(false);
  useFocusEffect(useCallback(() => {
    if (!mounted.current) { mounted.current = true; return; }
    latest.current();
  }, []));
}

/**
 * 독립적인 요청을 동시에 보내고, 일부가 실패해도 성공한 값은 보여준다 (실패한 항목은 null).
 * 모두 실패했을 때만 오류로 던진다. 첫 실패는 `failed`로 돌려준다.
 */
export async function settled<T extends Record<string, Promise<unknown>>>(calls: T): Promise<{ [K in keyof T]: Awaited<T[K]> | null } & { failed: unknown }> {
  const keys = Object.keys(calls);
  const results = await Promise.allSettled(keys.map((k) => calls[k]));
  const rejected = results.filter((r): r is PromiseRejectedResult => r.status === "rejected");
  if (keys.length && rejected.length === keys.length) throw rejected[0].reason;
  const out: Record<string, unknown> = { failed: rejected[0]?.reason ?? null };
  results.forEach((r, i) => { out[keys[i]] = r.status === "fulfilled" ? r.value : null; });
  return out as { [K in keyof T]: Awaited<T[K]> | null } & { failed: unknown };
}

export const errorMessage = (e: unknown) => {
  if (e instanceof ApiError) return e.status === 422 && typeof e.detail === "string" ? e.detail : e.title;
  if (e instanceof Error && e.name === "AbortError") return "응답이 늦어지고 있어요. 다시 시도해 주세요";
  if (e instanceof TypeError) return "네트워크 연결을 확인해 주세요";
  return e instanceof Error ? e.message : "잠시 후 다시 시도해 주세요";
};

/** 잠깐 보였다 사라지는 안내문 (공유 복사 등). 같은 문구를 다시 띄워도 타이머가 새로 돈다 */
export function useToast(durationMs = 3000): [string | null, (message: string | null) => void] {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const show = useCallback((next: string | null) => {
    if (timer.current) clearTimeout(timer.current);
    setMessage(next);
    if (next) timer.current = setTimeout(() => setMessage(null), durationMs);
  }, [durationMs]);
  return [message, show];
}

/**
 * 웹에서만: 없는 장소·없는 페이지처럼 색인되면 안 되는 상태에 <meta name="robots" content="noindex"> 와 제목을 붙인다.
 * SPA 라우트는 서버가 200으로 답하므로(soft-404) 크롤러에게 문서 안에서 알린다. 상태가 풀리거나 화면을 떠나면 되돌린다.
 */
export function useNoIndex(active: boolean, title?: string) {
  useEffect(() => {
    if (!active || typeof document === "undefined") return;
    const meta = document.createElement("meta");
    meta.name = "robots"; meta.content = "noindex";
    document.head.appendChild(meta);
    const previous = document.title;
    if (title) document.title = title;
    return () => { meta.remove(); if (title) document.title = previous; };
  }, [active, title]);
}
