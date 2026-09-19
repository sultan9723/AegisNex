import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

describe("runtime API proxy", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.BACKEND_INTERNAL_URL = "https://backend.example.test";
  });

  it("reads the backend URL at request time and forwards query, auth, cookie, and response data", async () => {
    const backendResponse = new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: {
        "content-type": "application/json",
        "set-cookie": "session=abc; Path=/; HttpOnly",
      },
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(backendResponse);
    const request = new Request("https://frontend.example.test/api/auth/verify?next=%2Fdashboard", {
      headers: {
        authorization: "Bearer token",
        cookie: "session=abc",
      },
    });

    const response = await GET(request as never, {
      params: Promise.resolve({ path: ["auth", "verify"] }),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://backend.example.test/api/auth/verify?next=%2Fdashboard",
      expect.objectContaining({ method: "GET" }),
    );
    const forwarded = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(forwarded.headers).get("authorization")).toBe("Bearer token");
    expect(new Headers(forwarded.headers).get("cookie")).toBe("session=abc");
    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("session=abc");
    await expect(response.json()).resolves.toEqual({ ok: true });
  });

  it("forwards POST bodies and uses a runtime environment change", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("created", { status: 201 }),
    );
    process.env.BACKEND_INTERNAL_URL = "https://new-backend.example.test/";
    const request = new Request("https://frontend.example.test/api/auth/demo-login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ demo: true }),
    });

    const response = await POST(request as never, {
      params: Promise.resolve({ path: ["auth", "demo-login"] }),
    });

    const [target, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(target).toBe("https://new-backend.example.test/api/auth/demo-login");
    expect(init.method).toBe("POST");
    expect(await new Response(init.body).text()).toBe('{"demo":true}');
    expect(response.status).toBe(201);
  });

  it("returns a clear unavailable response when the runtime URL is missing", async () => {
    delete process.env.BACKEND_INTERNAL_URL;

    const response = await GET(new Request("https://frontend.example.test/api/health") as never, {
      params: Promise.resolve({ path: ["health"] }),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ detail: "Backend proxy is not configured" });
  });
});
