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
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/command/start");
    expect(init).toMatchObject({ method: "POST" });
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("postCommand('abort') calls exactly POST /api/command/abort", async () => {
    const fetchMock = mockFetchOnce({ status: "ok", command: "abort" });
    await postCommand("abort");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/command/abort");
    expect(init).toMatchObject({ method: "POST" });
    expect(init.signal).toBeInstanceOf(AbortSignal);
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

  it("postCommand surfaces the backend's structured detail message on a non-OK status", async () => {
    mockFetchOnce({ detail: "not connected to rosbridge -- command not sent" }, false, 503);
    await expect(postCommand("abort")).rejects.toThrow(
      "POST /api/command/abort failed: HTTP 503: not connected to rosbridge -- command not sent",
    );
  });

  it("postCommand falls back to a bare HTTP status when the error body has no detail field", async () => {
    mockFetchOnce({}, false, 500);
    await expect(postCommand("start")).rejects.toThrow("POST /api/command/start failed: HTTP 500");
  });

  it("postCommand('start') rejects with a clear timeout error at 5000ms instead of hanging forever", async () => {
    vi.useFakeTimers();
    // A fetch that never resolves on its own, but honours the
    // AbortSignal like a real fetch implementation would -- this is what
    // lets postCommand's timeout actually unblock the caller.
    const fetchMock = vi.fn((_path: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const pending = expect(postCommand("start")).rejects.toThrow(/timed out after 5000ms/);
    await vi.advanceTimersByTimeAsync(5000);
    await pending;

    vi.useRealTimers();
  });

  it("postCommand('abort') times out much sooner (1500ms), not the 5000ms START bound", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((_path: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const pending = expect(postCommand("abort")).rejects.toThrow(/timed out after 1500ms/);
    await vi.advanceTimersByTimeAsync(1500);
    await pending;

    vi.useRealTimers();
  });

  it("does not abort postCommand('abort') early -- it still hasn't fired by 1000ms", async () => {
    vi.useFakeTimers();
    let aborted = false;
    const fetchMock = vi.fn((_path: string, init?: RequestInit) => {
      return new Promise(() => {
        init?.signal?.addEventListener("abort", () => {
          aborted = true;
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    postCommand("abort").catch(() => {});
    await vi.advanceTimersByTimeAsync(1000);
    expect(aborted).toBe(false);

    vi.useRealTimers();
  });
});
