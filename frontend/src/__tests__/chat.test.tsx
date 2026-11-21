import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Metadata } from "../types";

const live: Metadata = {
  resolution_source: "LIVE_INFERENCE", model: "gemini/test-model", latency_ms: 812,
  input_tokens: 42, output_tokens: 9, key_id: "key_1", fallback_attempts: 0,
};

type Handler = (body: any, headers: Record<string, string>) => { status: number; json: unknown };
let chatHandler: Handler;
let health = { status: "ok", keys_configured: 2, cache_enabled: true, failure_simulation: true };
let calls: { body: any; headers: Record<string, string> }[] = [];

beforeEach(() => {
  calls = [];
  health = { status: "ok", keys_configured: 2, cache_enabled: true, failure_simulation: true };
  chatHandler = (body) => ({ status: 200, json: { session_id: body.session_id, reply: "The capital of France is **Paris**.", metadata: live } });
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === "/health") return new Response(JSON.stringify(health), { status: 200 });
    if (path === "/chat") {
      const body = JSON.parse(String(init?.body));
      const headers = (init?.headers ?? {}) as Record<string, string>;
      calls.push({ body, headers });
      const r = chatHandler(body, headers);
      return new Response(JSON.stringify(r.json), { status: r.status });
    }
    return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function send(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByTestId("chat-input"), text);
  await user.click(screen.getByTestId("send-button"));
}

describe("frontend contract", () => {
  it("renders every required data-testid with real values inside the assistant message", async () => {
    render(<App />);
    expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    expect(screen.getByTestId("send-button")).toBeInTheDocument();
    expect(screen.getByTestId("system-prompt-input")).toBeInTheDocument();
    await send("What is the capital of France?");
    const msg = await screen.findByTestId("assistant-message");
    const q = within(msg);
    expect(q.getByTestId("meta-source")).toHaveTextContent(/^LIVE_INFERENCE$/);
    expect(q.getByTestId("meta-model")).toHaveTextContent(/^gemini\/test-model$/);
    expect(q.getByTestId("meta-latency")).toHaveTextContent(/^812 ms$/);
    expect(q.getByTestId("meta-input-tokens")).toHaveTextContent(/^42$/);
    expect(q.getByTestId("meta-output-tokens")).toHaveTextContent(/^9$/);
    expect(q.getByTestId("meta-key-id")).toHaveTextContent(/^key_1$/);
    expect(msg).toHaveTextContent("Paris");               // markdown rendered, reply text inside the container
    expect(msg.querySelector("strong")?.textContent).toBe("Paris");
  });

  it("clears the input after sending, and Enter sends", async () => {
    render(<App />);
    const user = userEvent.setup();
    const input = screen.getByTestId("chat-input") as HTMLTextAreaElement;
    await user.type(input, "hello{Enter}");
    expect(input.value).toBe("");
    await screen.findByTestId("assistant-message");
    expect(calls).toHaveLength(1);
    expect(calls[0].body.message).toBe("hello");
  });

  it("Shift+Enter adds a newline instead of sending", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId("chat-input"), "a{Shift>}{Enter}{/Shift}b");
    expect((screen.getByTestId("chat-input") as HTMLTextAreaElement).value).toBe("a\nb");
    expect(calls).toHaveLength(0);
  });

  it("send button is disabled for empty or whitespace-only input", async () => {
    render(<App />);
    const user = userEvent.setup();
    expect(screen.getByTestId("send-button")).toBeDisabled();
    await user.type(screen.getByTestId("chat-input"), "   ");
    expect(screen.getByTestId("send-button")).toBeDisabled();
  });

  it("cache hits show LLM_CACHE and key_id null", async () => {
    chatHandler = (b) => ({ status: 200, json: { session_id: b.session_id, reply: "Paris.", metadata: { ...live, resolution_source: "LLM_CACHE", key_id: null, latency_ms: 3 } } });
    render(<App />);
    await send("hi");
    const q = within(await screen.findByTestId("assistant-message"));
    expect(q.getByTestId("meta-source")).toHaveTextContent(/^LLM_CACHE$/);
    expect(q.getByTestId("meta-key-id")).toHaveTextContent(/^null$/);
    expect(q.getByTestId("meta-latency")).toHaveTextContent(/^3 ms$/);
  });

  it("shows the failover route derived from real metadata", async () => {
    chatHandler = (b) => ({ status: 200, json: { session_id: b.session_id, reply: "ok", metadata: { ...live, key_id: "key_2", fallback_attempts: 1 } } });
    render(<App />);
    await send("hi");
    const trace = await screen.findByTestId("route-trace");
    expect(trace).toHaveTextContent("key_1");
    expect(trace).toHaveTextContent("key_2");
  });
});

describe("errors never look like assistant replies", () => {
  it("renders a readable 422 message with the backend's reason", async () => {
    chatHandler = () => ({ status: 422, json: { detail: [{ loc: ["body", "message"], msg: "Value error, message must be 1-4000 characters after trimming" }] } });
    render(<App />);
    await send("x");
    const err = await screen.findByTestId("chat-error");
    expect(err).toHaveTextContent(/rejected this message/i);
    expect(err).toHaveTextContent(/message must be 1-4000/);
    expect(screen.queryByTestId("assistant-message")).toBeNull();
  });

  it("renders a readable 503 message and offers retry", async () => {
    chatHandler = () => ({ status: 503, json: { detail: "all providers unavailable" } });
    render(<App />);
    await send("hello");
    const err = await screen.findByTestId("chat-error");
    expect(err).toHaveTextContent(/All AI providers are unavailable/);
    expect(screen.queryByTestId("assistant-message")).toBeNull();
    chatHandler = (b) => ({ status: 200, json: { session_id: b.session_id, reply: "back", metadata: live } });
    await userEvent.setup().click(within(err).getByRole("button", { name: /retry/i }));
    await screen.findByTestId("assistant-message");
    expect(screen.queryByTestId("chat-error")).toBeNull();
    expect(calls).toHaveLength(2);
    expect(screen.getAllByTestId("user-message")).toHaveLength(1);   // retry reuses the same message
  });

  it("explains a network failure (backend down / CORS)", async () => {
    render(<App />);
    (fetch as any).mockImplementation(async (url: string) => {
      if (new URL(url).pathname === "/health") return new Response(JSON.stringify(health));
      throw new TypeError("Failed to fetch");
    });
    await send("hello");
    expect(await screen.findByTestId("chat-error")).toHaveTextContent(/Cannot reach the backend/);
  });
});

describe("sessions, system prompt and failure hook", () => {
  it("uses a different session id on every page load", async () => {
    const ids: string[] = [];
    for (let i = 0; i < 2; i++) {
      render(<App />);
      await send("hello");
      await screen.findByTestId("assistant-message");
      ids.push(calls[i].body.session_id);
      cleanup();
    }
    expect(ids[0]).not.toEqual(ids[1]);
    expect(ids[0].length).toBeGreaterThanOrEqual(1);
    expect(ids[0].length).toBeLessThanOrEqual(128);
  });

  it("sends the system prompt only when set", async () => {
    render(<App />);
    await send("one");
    await screen.findByTestId("assistant-message");
    expect(calls[0].body).not.toHaveProperty("system_prompt");
    await userEvent.setup().type(screen.getByTestId("system-prompt-input"), "Be a pirate");
    await send("two");
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1].body.system_prompt).toBe("Be a pirate");
  });

  it("arms X-Simulate-Failure for exactly one request", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "key_1=429" }));
    expect(screen.getByTestId("armed-failure")).toHaveTextContent("key_1=429");
    await send("first");
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].headers["X-Simulate-Failure"]).toBe("key_1=429");
    await screen.findAllByTestId("assistant-message");
    await send("second");
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1].headers["X-Simulate-Failure"]).toBeUndefined();
  });

  it("hides the failover controls when the server has simulation disabled", async () => {
    health.failure_simulation = false;
    render(<App />);
    expect(await screen.findByText(/Disabled on this server/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "key_1=429" })).toBeNull();
  });

  it("shows real backend health and logs only real requests", async () => {
    render(<App />);
    const info = await screen.findByTestId("health-info");
    await waitFor(() => expect(info).toHaveTextContent("Keys configured2"));
    expect(screen.queryByTestId("request-log")).toBeNull();      // nothing invented before any request
    await send("hello");
    const log = await screen.findByTestId("request-log");
    expect(log).toHaveTextContent("812 ms");
  });
});
