import { ApiError } from "@photospot/client";
import { useCallback, useEffect, useRef, useState } from "react";

/** 로딩·오류·재시도를 한 번에 다루는 작은 훅 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const run = useCallback(() => {
    const current = ++generation.current;
    setLoading(true); setError(null); setData(null);
    Promise.resolve().then(fn)
      .then((d) => { if (current === generation.current) setData(d); })
      .catch((e) => { if (current === generation.current) setError(e); })
      .finally(() => { if (current === generation.current) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); return () => { generation.current += 1; }; }, [run]);
  return { data, error, loading, reload: run };
}

export const errorMessage = (e: unknown) => {
  if (e instanceof ApiError) return e.status === 422 && typeof e.detail === "string" ? e.detail : e.title;
  if (e instanceof Error && e.name === "AbortError") return "응답이 늦어지고 있어요. 다시 시도해 주세요";
  if (e instanceof TypeError) return "네트워크 연결을 확인해 주세요";
  return e instanceof Error ? e.message : "잠시 후 다시 시도해 주세요";
};
