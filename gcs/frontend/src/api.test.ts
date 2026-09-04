import { afterEach, describe, expect, it, vi } from "vitest";
import { getTelemetry, postCommand } from "./api";

// Direct replacement for the old prototype's raw-HTML string-matching
// test -- verifies api.ts calls exactly the documented root-relative
// paths, with no host, matching gcs/backend/app/schemas.py's contract.

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api.ts", () => {
  it("getTelemetry calls exactly /api/telemetry", async () => {
    const fetchMock = mockFetchOnce({ connected: true });
    await getTelemetry();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/telemetry");
  });

  it("postCommand('start') calls exactly POST /api/command/start", async () => {
    const fetchMock = mockFetchOnce({ status: "ok", command: "start" });
    await postCommand("start");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/command/start", { method: "POST" });
  });

  it("postCommand('abort') calls exactly POST /api/command/abort", async () => {
    const fetchMock = mockFetchOnce({ status: "ok", command: "abort" });
    await postCommand("abort");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/command/abort", { method: "POST" });
  });

  it("no call ever uses an absolute URL with a host", async () => {
    const fetchMock = mockFetchOnce({ status: "ok", command: "start" });
    await postCommand("start");
    const [url] = fetchMock.mock.calls[0];
    expect(url).not.toMatch(/^https?:\/\//);
    expect((url as string).startsWith("/")).toBe(true);
  });

  it("rejects with a clear error on a non-OK HTTP status", async () => {
    mockFetchOnce({}, false, 503);
    await expect(getTelemetry()).rejects.toThrow(/503/);
  });
});
