import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "./api";
import { getAccessToken } from "./auth";

export type ConnectionStatus = "Connected" | "Reconnecting" | "Disconnected";

function getWebSocketUrl(path: string): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "");
  const token = getAccessToken();
  if (configured) return `${configured}${path}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
  const url = new URL(API_BASE_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = path;
  url.search = "";
  url.hash = "";
  if (token) url.searchParams.set("token", token);
  return url.toString();
}

type MessageHandler = (data: unknown) => void;

export function useWebSocket(
  path: string,
  onMessage: MessageHandler,
  enabled: boolean = true,
): ConnectionStatus {
  const [status, setStatus] = useState<ConnectionStatus>("Disconnected");
  const reconnectAttempt = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<number | null>(null);
  const closedByComponent = useRef(false);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    closedByComponent.current = false;
    setStatus("Reconnecting");
    const socket = new WebSocket(getWebSocketUrl(path));
    socketRef.current = socket;

    socket.onopen = () => {
      reconnectAttempt.current = 0;
      setStatus("Connected");
    };

    socket.onmessage = (event) => {
      try {
        onMessageRef.current(JSON.parse(event.data));
      } catch {
        // ignore parse errors
      }
    };

    socket.onclose = () => {
      if (closedByComponent.current) {
        setStatus("Disconnected");
        return;
      }
      reconnectAttempt.current += 1;
      setStatus("Reconnecting");
      const delay = Math.min(10000, 1000 * 2 ** Math.min(reconnectAttempt.current, 4));
      timerRef.current = window.setTimeout(connect, delay);
    };

    socket.onerror = () => socket?.close();
  }, [path]);

  useEffect(() => {
    if (!enabled) return;
    closedByComponent.current = false;
    connect();
    return () => {
      closedByComponent.current = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      socketRef.current?.close();
      setStatus("Disconnected");
    };
  }, [connect, enabled]);

  return status;
}
