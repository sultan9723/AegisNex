"use client";

import { createContext, useContext, useCallback, type ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { buildApiUrl } from "@/lib/api";

export type SessionInfo = {
  id: number;
  created_at: string;
  last_used_at: string | null;
  ip_address: string;
  user_agent: string;
  is_active: boolean;
};

type SessionContextValue = {
  listSessions: () => Promise<SessionInfo[]>;
  revokeSession: (sessionId: number) => Promise<void>;
  revokeAllSessions: () => Promise<number>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionManagerProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();

  const listSessions = useCallback(async (): Promise<SessionInfo[]> => {
    if (!isAuthenticated) return [];
    const res = await fetch(buildApiUrl("/sessions"), {
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) throw new Error("Failed to list sessions");
    const data = await res.json();
    return data.sessions ?? [];
  }, [isAuthenticated]);

  const revokeSession = useCallback(async (sessionId: number) => {
    const res = await fetch(buildApiUrl(`/sessions/${sessionId}`), {
      method: "DELETE",
      credentials: "include",
    });
    if (!res.ok) throw new Error("Failed to revoke session");
  }, []);

  const revokeAllSessions = useCallback(async (): Promise<number> => {
    const res = await fetch(buildApiUrl("/sessions"), {
      method: "DELETE",
      credentials: "include",
    });
    if (!res.ok) throw new Error("Failed to revoke sessions");
    const data = await res.json();
    return data.revoked_count ?? 0;
  }, []);

  return (
    <SessionContext.Provider value={{ listSessions, revokeSession, revokeAllSessions }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSessionManager(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSessionManager must be used within SessionManagerProvider");
  return ctx;
}
