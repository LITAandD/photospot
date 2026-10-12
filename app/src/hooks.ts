import { ApiError } from "@photospot/client";
import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 로딩·오류·재시도를 한 번에 다루는 작은 훅.
 * 다시 불러오는 동안 이전 data를 유지한다 (stale-while-revalidate): 화면이 비거나 스크롤이 튀지 않는다.
 * 첫 로딩 표시는 `loading && !data`로 판단한다.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const run = useCallback(() => {
    const current = ++generation.current;
    setLoading(true); setError(null);
    Promise.resolve().then(fn)
      .then((d) => { if (current === generation.current) setData(d); })
      .catch((e) => { if (current === generation.current) setError(e); })
      .finally(() => { if (current === generation.current) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); return () => { generation.current += 1; }; }, [run]);
  return { data, error, loading, reload: run };
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
