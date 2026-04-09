import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUpload } from "./useUpload";

/**
 * Mock de XMLHttpRequest pour tester useUpload sans faire de vraies requêtes.
 * Permet de simuler le cycle progression → load/error.
 */
class MockXHR {
  upload: { addEventListener: (event: string, cb: (e: ProgressEvent) => void) => void };
  responseText = "";
  status = 200;
  private _listeners: Record<string, ((e?: Event) => void)[]> = {};
  private _uploadListeners: Record<string, ((e: ProgressEvent) => void)[]> = {};

  constructor() {
    this.upload = {
      addEventListener: (event, cb) => {
        this._uploadListeners[event] ||= [];
        this._uploadListeners[event].push(cb);
      },
    };
  }

  addEventListener(event: string, cb: (e?: Event) => void): void {
    this._listeners[event] ||= [];
    this._listeners[event].push(cb);
  }

  open(): void {
    // no-op
  }
  setRequestHeader(): void {
    // no-op
  }
  send(): void {
    // Contrôlé manuellement par les tests via simulateProgress/simulateLoad.
  }

  simulateProgress(loaded: number, total: number): void {
    const event = { lengthComputable: true, loaded, total } as ProgressEvent;
    this._uploadListeners.progress?.forEach((cb) => cb(event));
  }

  simulateLoad(status: number, body: string): void {
    this.status = status;
    this.responseText = body;
    this._listeners.load?.forEach((cb) => cb());
  }

  simulateError(): void {
    this._listeners.error?.forEach((cb) => cb());
  }
}

describe("useUpload", () => {
  let mockXhr: MockXHR;

  beforeEach(() => {
    mockXhr = new MockXHR();
    // XMLHttpRequest doit être constructible avec `new` — on expose une classe
    // qui retourne toujours la même instance mockée (pour que le test puisse
    // ensuite interagir avec elle via simulateProgress/simulateLoad).
    class XHRStub {
      constructor() {
        return mockXhr as unknown as XHRStub;
      }
    }
    vi.stubGlobal("XMLHttpRequest", XHRStub);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("should start with idle state", () => {
    const { result } = renderHook(() => useUpload());

    expect(result.current.isUploading).toBe(false);
    expect(result.current.progress).toBe(0);
    expect(result.current.error).toBeNull();
  });

  it("should track upload progress", async () => {
    const { result } = renderHook(() => useUpload());
    const file = new File(["data"], "test.png", { type: "image/png" });

    act(() => {
      void result.current.upload(file);
    });

    await waitFor(() => expect(result.current.isUploading).toBe(true));

    act(() => {
      mockXhr.simulateProgress(50, 100);
    });

    expect(result.current.progress).toBe(50);
  });

  it("should resolve with the upload result on success", async () => {
    const { result } = renderHook(() => useUpload());
    const file = new File(["data"], "test.png", { type: "image/png" });

    let uploadPromise: Promise<unknown>;
    act(() => {
      uploadPromise = result.current.upload(file);
    });

    act(() => {
      mockXhr.simulateLoad(
        200,
        JSON.stringify({
          key: "uploads/abc.png",
          filename: "test.png",
          size: 4,
          content_type: "image/png",
        }),
      );
    });

    await expect(uploadPromise!).resolves.toMatchObject({
      key: "uploads/abc.png",
      filename: "test.png",
    });

    await waitFor(() => expect(result.current.isUploading).toBe(false));
    expect(result.current.progress).toBe(100);
    expect(result.current.error).toBeNull();
  });

  it("should set error on HTTP failure", async () => {
    const { result } = renderHook(() => useUpload());
    const file = new File(["data"], "test.png", { type: "image/png" });

    const uploadPromise = result.current.upload(file).catch(() => {
      // Erreur attendue, on l'absorbe.
    });

    act(() => {
      mockXhr.simulateLoad(413, "Too large");
    });

    await uploadPromise;

    await waitFor(() => {
      expect(result.current.error).toMatch(/413/);
      expect(result.current.isUploading).toBe(false);
    });
  });

  it("should set error on network failure", async () => {
    const { result } = renderHook(() => useUpload());
    const file = new File(["data"], "test.png", { type: "image/png" });

    const uploadPromise = result.current.upload(file).catch(() => {
      // Erreur attendue.
    });

    act(() => {
      mockXhr.simulateError();
    });

    await uploadPromise;

    await waitFor(() => {
      expect(result.current.error).toMatch(/Erreur réseau/);
    });
  });

  it("should reset state", () => {
    const { result } = renderHook(() => useUpload());

    act(() => {
      result.current.reset();
    });

    expect(result.current.isUploading).toBe(false);
    expect(result.current.progress).toBe(0);
    expect(result.current.error).toBeNull();
  });
});
