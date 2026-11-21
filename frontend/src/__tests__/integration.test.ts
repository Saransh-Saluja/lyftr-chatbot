/**
 * Runs the frontend's REAL api.ts against a REAL backend process.
 * Skipped unless INTEGRATION=1 (see scripts/e2e_local.sh). Node's fetch does not
 * enforce CORS, so CORS is verified separately (smoke_test.py --origin).
 */
import { describe, expect, it } from "vitest";
import { ApiError, getHealth, getHistory, postChat } from "../api";

const run = Math.random().toString(36).slice(2, 8);

describe.skipIf(!process.env.INTEGRATION)("api.ts against a live backend", () => {
  it("health", async () => {
    const h = await getHealth();
    expect(h.status).toBe("ok");
    expect(h.keys_configured).toBeGreaterThanOrEqual(2);
    expect(h.failure_simulation).toBe(true);
  });

  it("live -> cache across sessions, then stored history", async () => {
    const msg = `integration ${run}: capital of France?`;
    const a = await postChat({ session_id: `int-a-${run}`, message: msg });
    const b = await postChat({ session_id: `int-b-${run}`, message: msg });
    expect(a.metadata.resolution_source).toBe("LIVE_INFERENCE");
    expect(b.metadata.resolution_source).toBe("LLM_CACHE");
    expect(b.reply).toBe(a.reply);
    expect(b.metadata.key_id).toBeNull();
    const h = await getHistory(`int-b-${run}`);
    expect(h.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
  });

  it("failover header: key_2 answers with 1 fallback", async () => {
    const r = await postChat({ session_id: `int-f-${run}`, message: `failover ${run}` }, "key_1=429");
    expect(r.metadata.key_id).toBe("key_2");
    expect(r.metadata.fallback_attempts).toBe(1);
  });

  it("422 and 503 become readable ApiErrors", async () => {
    const e422 = await postChat({ session_id: `int-v-${run}`, message: "   " }).catch((e) => e);
    expect(e422).toBeInstanceOf(ApiError);
    expect(e422.status).toBe(422);
    expect(e422.message).toMatch(/rejected this message/);
    const e503 = await postChat({ session_id: `int-x-${run}`, message: `all fail ${run}` }, "*=429").catch((e) => e);
    expect(e503.status).toBe(503);
    expect(e503.message).toMatch(/All AI providers are unavailable/);
    const e404 = await getHistory(`int-x-${run}`).catch((e) => e);
    expect(e404.status).toBe(404);
  });
});
