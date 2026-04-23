import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUpdater } from "./useUpdater";
import { useUpdaterStore } from "@/stores/useUpdaterStore";

vi.mock("@/lib/tauri", async () => {
  const actual = await vi.importActual<typeof import("@/lib/tauri")>("@/lib/tauri");
  return {
    ...actual,
    isTauri: vi.fn(() => true),
  };
});

vi.mock("@tauri-apps/plugin-updater", () => ({
  check: vi.fn().mockResolvedValue(null),
}));

vi.mock("@tauri-apps/plugin-process", () => ({
  relaunch: vi.fn().mockResolvedValue(undefined),
}));

describe("useUpdater", () => {
  beforeEach(() => {
    useUpdaterStore.setState({
      phase: "idle",
      update: null,
      progress: { downloaded: 0, total: 0 },
      error: null,
      checkedOnce: false,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should trigger checkNow on first mount", async () => {
    const checkSpy = vi.spyOn(useUpdaterStore.getState(), "checkNow");

    renderHook(() => useUpdater());

    await waitFor(() => {
      expect(useUpdaterStore.getState().checkedOnce).toBe(true);
    });

    checkSpy.mockRestore();
  });

  it("should NOT trigger checkNow if already checked", async () => {
    useUpdaterStore.setState({ checkedOnce: true });

    const { check } = await import("@tauri-apps/plugin-updater");
    vi.mocked(check).mockClear();

    renderHook(() => useUpdater());

    await new Promise((r) => setTimeout(r, 20));
    expect(check).not.toHaveBeenCalled();
  });

  it("should expose the current store state", () => {
    useUpdaterStore.setState({
      phase: "available",
      update: { version: "0.2.0", currentVersion: "0.1.0" },
      checkedOnce: true,
    });

    const { result } = renderHook(() => useUpdater());

    expect(result.current.phase).toBe("available");
    expect(result.current.update?.version).toBe("0.2.0");
  });

  it("should be idempotent across re-renders of the same component", async () => {
    const { check } = await import("@tauri-apps/plugin-updater");
    vi.mocked(check).mockClear();

    const { rerender } = renderHook(() => useUpdater());

    await waitFor(() => {
      expect(useUpdaterStore.getState().checkedOnce).toBe(true);
    });

    // Forcer plusieurs re-renders — le hook ne doit pas re-déclencher le check.
    rerender();
    rerender();
    rerender();

    expect(check).toHaveBeenCalledTimes(1);
  });
});
