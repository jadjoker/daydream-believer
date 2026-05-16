"use client";
import { useState, useEffect, useCallback, useRef } from "react";

interface UseDataOptions {
  refreshInterval?: number;
  enabled?: boolean;
}

export function useData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  options: UseDataOptions = {}
) {
  const { refreshInterval, enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetch = useCallback(async () => {
    if (!enabled) return;
    try {
      setError(null);
      const result = await fetcher();
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => {
    setLoading(true);
    setData(null); // clear stale data so previous ticker never shows through
    fetch();
    if (refreshInterval) {
      timerRef.current = setInterval(fetch, refreshInterval);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetch, refreshInterval]);

  return { data, loading, error, refetch: fetch };
}
