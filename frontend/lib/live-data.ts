"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL, DEFAULT_TIMEOUT_MS } from "@/lib/api";

type Fetcher<T> = () => Promise<T>;

type LiveDataOptions = {
  pollIntervalMs?: number;
  enabled?: boolean;
};

export function useLiveData<T>(
  key: string,
  fetcher: Fetcher<T>,
  wsPath?: string,
  wsEventType?: string,
  options: LiveDataOptions = {},
) {
  const { pollIntervalMs = 15000, enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(async () => {
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    load();
  }, [enabled, load, key]);

  useEffect(() => {
    if (!enabled || !wsPath) return;

    const protocol = API_BASE_URL.startsWith("https") ? "wss" : "ws";
    const base = API_BASE_URL.replace(/^https?:\/\//, "");
    const url = `${protocol}://${base}${wsPath}`;

    let closed = false;
    const connect = () => {
      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;
        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (!wsEventType || msg.type === wsEventType) {
              setData(msg.payload ?? msg);
              setError(null);
            }
          } catch { /* ignore parse errors */ }
        };
        ws.onclose = () => {
          if (!closed) setTimeout(connect, 5000);
        };
        ws.onerror = () => ws.close();
      } catch { /* ignore connection errors */ }
    };
    connect();
    return () => { closed = true; wsRef.current?.close(); };
  }, [enabled, wsPath, wsEventType]);

  useEffect(() => {
    if (!enabled || !pollIntervalMs || wsPath) return;
    pollRef.current = setInterval(load, pollIntervalMs);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [enabled, pollIntervalMs, wsPath, load]);

  return { data, loading, error, refresh: load };
}
