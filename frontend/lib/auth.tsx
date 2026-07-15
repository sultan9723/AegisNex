"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
let currentAccessToken: string | null = null;

function setCurrentAccessToken(token: string | null) {
  currentAccessToken = token;
  if (typeof window !== "undefined") {
    (window as any).__AEGISNEX_ACCESS_TOKEN__ = token;
  }
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
  logout: () => Promise<void>;
  isAuthenticated: boolean;
  checkAuth: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkAuth = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/api/auth/verify`, {
        credentials: "include",
        cache: "no-store",
      });
      if (response.ok) {
        const data = await response.json();
        setUser(data.user);
        setCurrentAccessToken(data.access_token ?? currentAccessToken);
        setError(null);
      } else {
        setUser(null);
        setCurrentAccessToken(null);
      }
    } catch {
      setUser(null);
      setCurrentAccessToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username, password }),
        credentials: "include",
      });
      if (!response.ok) throw new Error("Invalid credentials");
      const data = await response.json();
      setCurrentAccessToken(data.access_token ?? null);
      const parts = data.access_token.split(".");
      let userInfo: User;
      try {
        const payload = JSON.parse(atob(parts[1]));
        userInfo = {
          id: parseInt(payload.sub),
          email: payload.email,
          role: payload.role,
          is_superuser: payload.is_superuser,
        };
      } catch {
        userInfo = { id: 0, email: username, role: "read_only", is_superuser: false };
      }
      setUser(userInfo);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/logout`, { credentials: "include" });
    } catch {
      // Best-effort
    }
    setUser(null);
    setCurrentAccessToken(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        login,
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

export function getAccessToken(): string | null {
  return currentAccessToken;
}
