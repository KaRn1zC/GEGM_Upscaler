import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTauriDragDrop } from "./useTauriDragDrop";

/**
 * Tests du hook Tauri drag-drop. Tous les `await import()` internes au hook
 * sont interceptés par `vi.mock` ci-dessous — le code réel du plugin
 * `@tauri-apps/api/window` n'est jamais chargé en test.
 */

// Capture la dernière callback passée à `onDragDropEvent` pour qu'on puisse
// l'invoquer manuellement depuis les tests (simulation d'un drop natif).
const state: {
  handler: ((event: DragDropEvent) => void) | null;
  dispose: ReturnType<typeof vi.fn>;
} = {
  handler: null,
  dispose: vi.fn(),
};

interface DragDropEvent {
  payload:
    | { type: "enter" | "over" | "leave" }
    | { type: "drop"; paths: string[] };
}

vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    onDragDropEvent: vi.fn(async (cb: (event: DragDropEvent) => void) => {
      state.handler = cb;
      return state.dispose;
    }),
  }),
}));

vi.mock("@/lib/tauri", async () => {
  const actual = await vi.importActual<typeof import("@/lib/tauri")>("@/lib/tauri");
  return {
    ...actual,
    isTauri: vi.fn(() => true),
    readFileFromPath: vi.fn(async (path: string) => {
      return new File([new Uint8Array([1, 2, 3])], path.split("/").pop() ?? path, {
        type: "image/png",
      });
    }),
  };
});

describe("useTauriDragDrop", () => {
  beforeEach(() => {
    state.handler = null;
    state.dispose = vi.fn();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it("should register a drag-drop listener when running in Tauri", async () => {
    renderHook(() => useTauriDragDrop(vi.fn()));
    await waitFor(() => expect(state.handler).not.toBeNull());
  });

  it("should forward dropped files to the callback", async () => {
    const onFilesDropped = vi.fn();
    renderHook(() => useTauriDragDrop(onFilesDropped));

    await waitFor(() => expect(state.handler).not.toBeNull());

    state.handler!({
      payload: { type: "drop", paths: ["/tmp/a.png", "/tmp/b.jpg"] },
    });

    await waitFor(() => expect(onFilesDropped).toHaveBeenCalledTimes(1));
    const files = onFilesDropped.mock.calls[0][0] as File[];
    expect(files).toHaveLength(2);
    expect(files[0].name).toBe("a.png");
  });

  it("should filter out files with unsupported extensions", async () => {
    const onFilesDropped = vi.fn();
    renderHook(() => useTauriDragDrop(onFilesDropped));

    await waitFor(() => expect(state.handler).not.toBeNull());

    state.handler!({
      payload: { type: "drop", paths: ["/tmp/a.png", "/tmp/b.pdf", "/tmp/c.exe"] },
    });

    await waitFor(() => expect(onFilesDropped).toHaveBeenCalledTimes(1));
    const files = onFilesDropped.mock.calls[0][0] as File[];
    expect(files).toHaveLength(1);
    expect(files[0].name).toBe("a.png");
  });

  it("should not invoke the callback when all files are filtered out", async () => {
    const onFilesDropped = vi.fn();
    renderHook(() => useTauriDragDrop(onFilesDropped));

    await waitFor(() => expect(state.handler).not.toBeNull());

    state.handler!({
      payload: { type: "drop", paths: ["/tmp/a.pdf", "/tmp/b.exe"] },
    });

    // Pas de callback → attendre un tick et vérifier qu'il n'a pas été appelé.
    await new Promise((r) => setTimeout(r, 10));
    expect(onFilesDropped).not.toHaveBeenCalled();
  });

  it("should ignore non-drop events (enter/over/leave)", async () => {
    const onFilesDropped = vi.fn();
    renderHook(() => useTauriDragDrop(onFilesDropped));

    await waitFor(() => expect(state.handler).not.toBeNull());

    state.handler!({ payload: { type: "enter" } });
    state.handler!({ payload: { type: "over" } });
    state.handler!({ payload: { type: "leave" } });

    await new Promise((r) => setTimeout(r, 10));
    expect(onFilesDropped).not.toHaveBeenCalled();
  });

  it("should unregister the listener on unmount", async () => {
    const { unmount } = renderHook(() => useTauriDragDrop(vi.fn()));
    await waitFor(() => expect(state.handler).not.toBeNull());
    unmount();
    expect(state.dispose).toHaveBeenCalledTimes(1);
  });

  it("should respect a custom accept list", async () => {
    const onFilesDropped = vi.fn();
    const accept = ["png"] as const;
    renderHook(() => useTauriDragDrop(onFilesDropped, accept));

    await waitFor(() => expect(state.handler).not.toBeNull());

    state.handler!({
      payload: { type: "drop", paths: ["/tmp/a.png", "/tmp/b.jpg"] },
    });

    await waitFor(() => expect(onFilesDropped).toHaveBeenCalledTimes(1));
    const files = onFilesDropped.mock.calls[0][0] as File[];
    expect(files).toHaveLength(1);
    expect(files[0].name).toBe("a.png");
  });
});

describe("useTauriDragDrop outside Tauri", () => {
  beforeEach(async () => {
    state.handler = null;
    state.dispose = vi.fn();
    vi.clearAllMocks();
    const tauri = await import("@/lib/tauri");
    vi.mocked(tauri.isTauri).mockReturnValue(false);
  });

  afterEach(async () => {
    const tauri = await import("@/lib/tauri");
    vi.mocked(tauri.isTauri).mockReturnValue(true);
  });

  it("should be a no-op when not running in Tauri", async () => {
    const onFilesDropped = vi.fn();
    renderHook(() => useTauriDragDrop(onFilesDropped));

    await new Promise((r) => setTimeout(r, 10));
    expect(state.handler).toBeNull();
    expect(onFilesDropped).not.toHaveBeenCalled();
  });
});
