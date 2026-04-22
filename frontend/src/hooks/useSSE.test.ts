import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSSE } from "./useSSE";
import * as api from "@/lib/api";

/**
 * Mock minimal d'`EventSource` — expose des hooks pour injecter des events
 * comme si le serveur les envoyait, et trace les appels à ``close()`` pour
 * vérifier qu'on ne ferme pas prématurément sur erreur réseau.
 */
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  closed = false;
  private _listeners: Record<string, ((e: unknown) => void)[]> = {};

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(event: string, cb: (e: unknown) => void): void {
    this._listeners[event] ||= [];
    this._listeners[event].push(cb);
  }

  close(): void {
    this.closed = true;
  }

  /** Injecte un event `progress`/`completed` avec un payload JSON. */
  emit(event: string, data: Record<string, unknown>): void {
    const payload = new MessageEvent(event, { data: JSON.stringify(data) });
    this._listeners[event]?.forEach((cb) => cb(payload));
  }

  /** Simule une erreur réseau (event `error` sans payload JSON). */
  emitNetworkError(): void {
    // Un Event nu, pas un MessageEvent — le hook doit distinguer ce cas.
    const evt = new Event("error");
    this._listeners.error?.forEach((cb) => cb(evt));
  }

  /** Simule une erreur applicative (event `error` avec payload JSON). */
  emitAppError(data: Record<string, unknown>): void {
    const payload = new MessageEvent("error", { data: JSON.stringify(data) });
    this._listeners.error?.forEach((cb) => cb(payload));
  }
}

describe("useSSE", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("should not subscribe when jobId is null", () => {
    renderHook(() =>
      useSSE({
        jobId: null,
        onProgress: vi.fn(),
        onComplete: vi.fn(),
        onError: vi.fn(),
      }),
    );
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it("should forward progress events to onProgress", () => {
    const onProgress = vi.fn();
    renderHook(() =>
      useSSE({
        jobId: "job-1",
        onProgress,
        onComplete: vi.fn(),
        onError: vi.fn(),
      }),
    );

    const es = MockEventSource.instances[0];
    expect(es).toBeDefined();
    act(() => {
      es.emit("progress", { job_id: "job-1", status: "processing", progress: 0.5 });
    });

    expect(onProgress).toHaveBeenCalledWith(
      expect.objectContaining({ job_id: "job-1", progress: 0.5 }),
    );
  });

  it("should close connection and call onComplete on completed event", () => {
    const onComplete = vi.fn();
    renderHook(() =>
      useSSE({
        jobId: "job-1",
        onProgress: vi.fn(),
        onComplete,
        onError: vi.fn(),
      }),
    );

    const es = MockEventSource.instances[0];
    act(() => {
      es.emit("completed", { job_id: "job-1", status: "completed", progress: 1.0 });
    });

    expect(onComplete).toHaveBeenCalled();
    expect(es.closed).toBe(true);
  });

  it("should NOT close connection on network error (lets EventSource auto-reconnect)", () => {
    const onError = vi.fn();
    renderHook(() =>
      useSSE({
        jobId: "job-1",
        onProgress: vi.fn(),
        onComplete: vi.fn(),
        onError,
      }),
    );

    const es = MockEventSource.instances[0];
    act(() => {
      es.emitNetworkError();
    });

    // Sans payload JSON, on considère que c'est une erreur réseau — la
    // connexion reste ouverte pour laisser EventSource reconnecter.
    expect(es.closed).toBe(false);
    expect(onError).not.toHaveBeenCalled();
  });

  it("should close and call onError on app-level error event", () => {
    const onError = vi.fn();
    renderHook(() =>
      useSSE({
        jobId: "job-1",
        onProgress: vi.fn(),
        onComplete: vi.fn(),
        onError,
      }),
    );

    const es = MockEventSource.instances[0];
    act(() => {
      es.emitAppError({
        job_id: "job-1",
        status: "failed",
        progress: 0,
        error_message: "GPU crashed",
      });
    });

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ status: "failed", error_message: "GPU crashed" }),
    );
    expect(es.closed).toBe(true);
  });

  it("should fetch job status from API as fallback after silence", async () => {
    const onComplete = vi.fn();
    const getJobSpy = vi.spyOn(api, "getJob").mockResolvedValue({
      id: "job-1",
      user_id: "u1",
      status: "completed",
      input_key: "uploads/a.png",
      output_key: "results/a.png",
      scale_factor: 4,
      model_name: "drct-l",
      input_width: 100,
      input_height: 100,
      output_width: 400,
      output_height: 400,
      gpu_backend: "cloud",
      progress: 1,
      error_message: null,
      prefer_local: null,
      created_at: "2026-04-22T00:00:00Z",
      updated_at: "2026-04-22T00:00:00Z",
      completed_at: "2026-04-22T00:01:00Z",
    });

    renderHook(() =>
      useSSE({
        jobId: "job-1",
        onProgress: vi.fn(),
        onComplete,
        onError: vi.fn(),
      }),
    );

    // Avance les timers au-delà du seuil de silence (45s) + un tick de check (15s).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    await waitFor(() => {
      expect(getJobSpy).toHaveBeenCalledWith("job-1");
      expect(onComplete).toHaveBeenCalledWith(
        expect.objectContaining({ job_id: "job-1", status: "completed" }),
      );
    });
  });

  it("should close EventSource on unmount", () => {
    const { unmount } = renderHook(() =>
      useSSE({
        jobId: "job-1",
        onProgress: vi.fn(),
        onComplete: vi.fn(),
        onError: vi.fn(),
      }),
    );

    const es = MockEventSource.instances[0];
    expect(es.closed).toBe(false);

    unmount();

    expect(es.closed).toBe(true);
  });
});
