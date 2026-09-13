import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import WorkforcePage, { WORKFORCE_PROVIDERS } from "./page";

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data),
  } as Response);
}

const emptyStats = {
  total_agents: 0,
  active_agents: 0,
  paused_agents: 0,
  draft_agents: 0,
  by_type: {},
  by_health: {},
  avg_trust_score: 50,
  total_executions: 0,
  total_successes: 0,
  total_failures: 0,
  total_cost: 0,
  avg_success_rate: 100,
};

describe("Workforce Create Agent Wizard provider options", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/workforce/stats")) {
        return jsonResponse(emptyStats);
      }
      if (url.includes("/api/workforce/agents")) {
        return jsonResponse({ agents: [], total: 0 });
      }
      return jsonResponse({});
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("exposes Groq and preserves all existing providers in the provider list", () => {
    const values = WORKFORCE_PROVIDERS.map((p) => p.value);
    expect(values).toContain("groq");
    for (const existing of ["openai", "anthropic", "google", "mistral", "local"]) {
      expect(values).toContain(existing);
    }
    expect(WORKFORCE_PROVIDERS.find((p) => p.value === "groq")?.label).toBe("Groq");
  });

  it("shows Groq as a selectable provider in the wizard", async () => {
    render(<WorkforcePage />);
    fireEvent.click(screen.getByText("Create Agent"));
    expect(screen.getByText("Create Agent Wizard")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Next"));

    const select = screen.getByRole("combobox") as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).toContain("groq");
    expect(optionValues).toEqual(
      expect.arrayContaining(["openai", "anthropic", "google", "groq", "mistral", "local"]),
    );
  });

  it("auto-fills a Groq model when Groq is selected and keeps custom choices", async () => {
    render(<WorkforcePage />);
    fireEvent.click(screen.getByText("Create Agent"));
    fireEvent.click(screen.getByText("Next"));

    const modelInput = screen.getByDisplayValue("gpt-4o-mini");
    expect(modelInput).toHaveValue("gpt-4o-mini");

    const select = screen.getByRole("combobox") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "groq" } });

    expect(screen.getByDisplayValue("openai/gpt-oss-20b")).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("openai/gpt-oss-20b"), { target: { value: "custom-model" } });
fireEvent.change(select, { target: { value: "openai" } });
    fireEvent.change(select, { target: { value: "groq" } });
    expect(screen.getByDisplayValue("custom-model")).toBeInTheDocument();
  });
});