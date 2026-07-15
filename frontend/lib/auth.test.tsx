import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { cleanup, render, act } from "@testing-library/react";

function createJWT(payload: Record<string, unknown>): string {
  const header = JSON.stringify({ alg: "HS256", typ: "JWT" });
  const body = JSON.stringify(payload);
  return `${btoa(header)}.${btoa(body)}.fake-sig`;
}

// Track login responses per test
let loginResponse: Response | null = null;
let demoLoginResponse: Response | null = null;

beforeEach(() => {
  vi.restoreAllMocks();
  loginResponse = null;
  demoLoginResponse = null;
  delete (globalThis as any).__AEGISNEX_ACCESS_TOKEN__;

  // Global fetch mock: checkAuth always returns 401, login returns the custom response
  globalThis.fetch = vi.fn().mockImplementation(async (url: string) => {
    if (url.includes("/api/login")) {
      return loginResponse ?? new Response("Unauthorized", { status: 401 });
    }
    if (url.includes("/api/auth/demo-login")) {
      return demoLoginResponse ?? new Response("Unauthorized", { status: 401 });
    }
    // Default: checkAuth and others return 401
    return new Response("Unauthorized", { status: 401 });
  });
});

afterEach(() => {
  cleanup();
});

// --- getAccessToken ---

describe("getAccessToken", () => {
  it("returns null when no token has been set", async () => {
    vi.resetModules();
    const { getAccessToken } = await import("./auth");
    expect(getAccessToken()).toBeNull();
  });

  it("does not leak token to window object", async () => {
    vi.resetModules();
    await import("./auth");
    expect((globalThis as any).__AEGISNEX_ACCESS_TOKEN__).toBeUndefined();
  });
});

// --- Login validation ---

describe("login error handling", () => {
  it("throws when access_token is missing from response", async () => {
    vi.resetModules();
    loginResponse = new Response(JSON.stringify({}), { status: 200 });

    const mod = await import("./auth");
    let caught: Error | null = null;

    function TestConsumer() {
      const auth = mod.useAuth();
      return React.createElement("button", {
        "data-testid": "login-btn",
        onClick: async () => {
          try { await auth.login("user", "pass"); }
          catch (e) { caught = e as Error; }
        },
      }, "Login");
    }

    render(React.createElement(mod.AuthProvider, null, React.createElement(TestConsumer)));

    const { screen } = await import("@testing-library/react");
    const btn = screen.getByTestId("login-btn");
    await act(async () => { btn.click(); });

    await vi.waitFor(() => {
      expect(caught).not.toBeNull();
      expect(caught!.message).toContain("no access token received");
    });
  });

  it("throws on HTTP 401", async () => {
    vi.resetModules();
    loginResponse = new Response("Unauthorized", { status: 401 });

    const mod = await import("./auth");
    let caught: Error | null = null;

    function TestConsumer() {
      const auth = mod.useAuth();
      return React.createElement("button", {
        "data-testid": "login-btn",
        onClick: async () => {
          try { await auth.login("user", "pass"); }
          catch (e) { caught = e as Error; }
        },
      }, "Login");
    }

    render(React.createElement(mod.AuthProvider, null, React.createElement(TestConsumer)));

    const { screen } = await import("@testing-library/react");
    const btn = screen.getByTestId("login-btn");
    await act(async () => { btn.click(); });

    await vi.waitFor(() => {
      expect(caught).not.toBeNull();
      expect(caught!.message).toBe("Invalid credentials");
    });
  });

  it("throws and clears state on malformed JWT", async () => {
    vi.resetModules();
    loginResponse = new Response(JSON.stringify({ access_token: "not-a-jwt" }), { status: 200 });

    const mod = await import("./auth");
    let caught: Error | null = null;

    function TestConsumer() {
      const auth = mod.useAuth();
      return React.createElement("button", {
        "data-testid": "login-btn",
        onClick: async () => {
          try { await auth.login("user", "pass"); }
          catch (e) { caught = e as Error; }
        },
      }, "Login");
    }

    render(React.createElement(mod.AuthProvider, null, React.createElement(TestConsumer)));

    const { screen } = await import("@testing-library/react");
    const btn = screen.getByTestId("login-btn");
    await act(async () => { btn.click(); });

    await vi.waitFor(() => {
      expect(caught).not.toBeNull();
      expect(caught!.message).toContain("malformed token");
    });
  });
});

// --- Successful login ---

describe("successful login", () => {
  it("authenticates user with valid JWT and sets the token", async () => {
    vi.resetModules();

    const token = createJWT({ sub: "1", email: "admin@aegisnex.io", role: "administrator", is_superuser: true });
    loginResponse = new Response(JSON.stringify({ access_token: token }), { status: 200 });

    const mod = await import("./auth");

    function TestConsumer() {
      const auth = mod.useAuth();
      return React.createElement("button", {
        "data-testid": "login-btn",
        onClick: async () => {
          await auth.login("admin", "pass");
        },
      }, auth.isAuthenticated ? `Logged in as ${auth.user?.email}` : "Login");
    }

    render(React.createElement(mod.AuthProvider, null, React.createElement(TestConsumer)));

    const { screen } = await import("@testing-library/react");
    const btn = screen.getByTestId("login-btn");
    await act(async () => { btn.click(); });

    await vi.waitFor(() => {
      const btnEl = screen.getByTestId("login-btn");
      expect(btnEl.textContent).toBe("Logged in as admin@aegisnex.io");
    });
  });
});

describe("demo login", () => {
  it("authenticates the seeded demo account without a frontend password literal", async () => {
    vi.resetModules();

    const token = createJWT({ sub: "1", email: "admin", role: "administrator", is_superuser: true });
    demoLoginResponse = new Response(JSON.stringify({ access_token: token }), { status: 200 });

    const mod = await import("./auth");

    function TestConsumer() {
      const auth = mod.useAuth();
      return React.createElement("button", {
        "data-testid": "demo-btn",
        onClick: async () => {
          await auth.demoLogin();
        },
      }, auth.isAuthenticated ? `Logged in as ${auth.user?.email}` : "Demo");
    }

    render(React.createElement(mod.AuthProvider, null, React.createElement(TestConsumer)));

    const { screen } = await import("@testing-library/react");
    const btn = screen.getByTestId("demo-btn");
    await act(async () => { btn.click(); });

    await vi.waitFor(() => {
      const btnEl = screen.getByTestId("demo-btn");
      expect(btnEl.textContent).toBe("Logged in as admin");
    });
  });
});

// --- Privilege escalation ---

describe("privilege escalation prevention", () => {
  it("does not create a fallback admin user on JWT parse failure", async () => {
    vi.resetModules();
    loginResponse = new Response(JSON.stringify({ access_token: "bad.token.here" }), { status: 200 });

    const mod = await import("./auth");
    let caught: Error | null = null;
    let capturedUser: any = null;
    let capturedAuthenticated: boolean | null = null;

    function TestConsumer() {
      const auth = mod.useAuth();
      capturedUser = auth.user;
      capturedAuthenticated = auth.isAuthenticated;
      return React.createElement("button", {
        "data-testid": "login-btn",
        onClick: async () => {
          try { await auth.login("user", "pass"); }
          catch (e) { caught = e as Error; }
        },
      }, "Login");
    }

    render(React.createElement(mod.AuthProvider, null, React.createElement(TestConsumer)));

    const { screen } = await import("@testing-library/react");
    const btn = screen.getByTestId("login-btn");
    await act(async () => { btn.click(); });

    await vi.waitFor(() => {
      expect(caught).not.toBeNull();
      expect(caught!.message).toContain("malformed token");
    });

    expect(capturedUser).toBeNull();
    expect(capturedAuthenticated).toBe(false);
  });
});
