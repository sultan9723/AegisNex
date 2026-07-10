"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { buildApiUrl } from "./api";
let currentAccessToken: string | null = null;

function setCurrentAccessToken(token: string | null) {
  currentAccessToken = token;
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const applyAuthResponse = useCallback(async (response: Response) => {
    if (!response.ok) throw new Error("Invalid credentials");
    const data = await response.json();
    if (!data.access_token) throw new Error("Authentication failed: no access token received");
    setCurrentAccessToken(data.access_token);
    const parts = data.access_token.split(".");
    try {
      const payload = JSON.parse(atob(parts[1]));
      const userInfo: User = {
        id: parseInt(payload.sub),
        email: payload.email,
        role: payload.role,
        is_superuser: payload.is_superuser,
      };
      setUser(userInfo);
      return;
    } catch {
      setCurrentAccessToken(null);
      setUser(null);
      setError("Authentication failed: malformed token");
      throw new Error("Authentication failed: malformed token");
    }
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(buildApiUrl("/auth/verify"), {
        credentials: "include",
        cache: "no-store",
      });
      if (response.ok) {
        const data = await response.json();
        setUser(data.user);
        setCurrentAccessToken(data.access_token ?? currentAccessToken);
        setError(null);
      } else {
        const refresh = await fetch(buildApiUrl("/auth/refresh"), {
          method: "POST",
          credentials: "include",
          cache: "no-store",
        });
        if (refresh.ok) {
          await applyAuthResponse(refresh);
          setError(null);
        } else {
          setUser(null);
          setCurrentAccessToken(null);
        }
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
      const response = await fetch(buildApiUrl("/login"), {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username, password }),
        credentials: "include",
      });
      await applyAuthResponse(response);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const demoLogin = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const response = await fetch(buildApiUrl("/auth/demo-login"), {
        method: "POST",
        credentials: "include",
      });
      await applyAuthResponse(response);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Demo login failed";
      setError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [applyAuthResponse]);

  const logout = useCallback(async () => {
    try {
      await fetch("/logout", { credentials: "include" });
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

export function getAccessToken(): string | null {
  return currentAccessToken;
}
