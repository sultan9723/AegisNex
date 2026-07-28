"use client";

import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { buildApiUrl } from "./api";

let currentAccessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;

function setCurrentAccessToken(token: string | null) {
  currentAccessToken = token;
}

export function getAccessToken(): string | null {
  return currentAccessToken;
}

export function setAccessToken(token: string | null) {
  currentAccessToken = token;
}

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export type User = {
  id: number;
  email: string;
  role: string;
  is_superuser: boolean;
};

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  demoLogin: () => Promise<void>;
  logout: () => Promise<void>;
  isAuthenticated: boolean;
  checkAuth: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function parseJwtPayload(token: string): User | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]));
    return {
      id: parseInt(payload.sub),
      email: payload.email,
      role: payload.role,
      is_superuser: payload.is_superuser,
    };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initDone = useRef(false);

  const applyToken = useCallback((token: string): User | null => {
    const parsed = parseJwtPayload(token);
    if (parsed) {
      currentAccessToken = token;
      setUser(parsed);
      setError(null);
    }
    return parsed;
  }, []);

  const clearAuth = useCallback(() => {
    currentAccessToken = null;
    setUser(null);
  }, []);

  const tryRefresh = useCallback(async (): Promise<boolean> => {
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => {
      try {
        const res = await fetch(buildApiUrl("/auth/refresh"), {
          method: "POST",
          credentials: "include",
          cache: "no-store",
        });
        if (!res.ok) return false;
        const data = await res.json();
        if (!data.access_token) return false;
        const parsed = applyToken(data.access_token);
        return parsed !== null;
      } catch {
        return false;
      } finally {
        refreshPromise = null;
      }
    })();
    return refreshPromise;
  }, [applyToken]);

  const checkAuth = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(buildApiUrl("/auth/verify"), {
        credentials: "include",
        cache: "no-store",
      });
      if (res.ok) {
        const data = await res.json();
        if (data.user) {
          setUser(data.user);
          setError(null);
        }
      } else {
        const refreshed = await tryRefresh();
        if (!refreshed) {
          clearAuth();
        }
      }
    } catch {
      clearAuth();
    } finally {
      setLoading(false);
    }
  }, [tryRefresh, clearAuth]);

  useEffect(() => {
    if (initDone.current) return;
    initDone.current = true;

    let cancelled = false;

    const init = async () => {
      try {
        setLoading(true);
        const res = await fetch(buildApiUrl("/auth/verify"), {
          credentials: "include",
          cache: "no-store",
        });
        if (cancelled) return;

        if (res.ok) {
          const data = await res.json();
          if (!cancelled && data.user) {
            setUser(data.user);
            setError(null);
          }
        } else {
          const refreshed = await tryRefresh();
          if (cancelled) return;
          if (!refreshed) {
            clearAuth();
          }
        }
      } catch {
        if (!cancelled) clearAuth();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    init();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    setLoading(true);
    try {
      const csrfToken = getCsrfToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/x-www-form-urlencoded",
      };
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }
      const res = await fetch(buildApiUrl("/login"), {
        method: "POST",
        headers,
        body: new URLSearchParams({ username, password }),
        credentials: "include",
      });
      if (!res.ok) {
        let detail = "Invalid credentials";
        try {
          const body = await res.json();
          if (body?.detail) detail = body.detail;
        } catch { /* ignore */ }
        throw new Error(detail);
      }
      const data = await res.json();
      if (!data.access_token) throw new Error("no access token received");
      if (!applyToken(data.access_token)) {
        clearAuth();
        throw new Error("malformed token");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [applyToken, clearAuth]);

  const demoLogin = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const csrfToken = getCsrfToken();
      const headers: Record<string, string> = {};
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }
      const res = await fetch(buildApiUrl("/auth/demo-login"), {
        method: "POST",
        headers,
        credentials: "include",
      });
      if (!res.ok) {
        let detail = "Demo login failed";
        try {
          const body = await res.json();
          if (body?.detail) detail = body.detail;
        } catch { /* ignore */ }
        throw new Error(detail);
      }
      const data = await res.json();
      if (!data.access_token) throw new Error("no access token received");
      if (!applyToken(data.access_token)) {
        clearAuth();
        throw new Error("malformed token");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Demo login failed";
      setError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [applyToken, clearAuth]);

  const logout = useCallback(async () => {
    try {
      await fetch(buildApiUrl("/logout"), {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Best-effort
    }
    clearAuth();
  }, [clearAuth]);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        login,
        demoLogin,
        logout,
        isAuthenticated: user !== null,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
