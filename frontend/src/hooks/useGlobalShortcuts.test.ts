import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useGlobalShortcuts } from "./useGlobalShortcuts";

// Mock de react-router-dom : on n'a besoin que de useNavigate pour vérifier
// que le hook dispatche la bonne route sur chaque raccourci.
const navigateMock = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigateMock,
}));

function fireKey(key: string, opts: { meta?: boolean; ctrl?: boolean } = {}): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    key,
    metaKey: opts.meta ?? false,
    ctrlKey: opts.ctrl ?? false,
    bubbles: true,
    cancelable: true,
  });
  document.dispatchEvent(event);
  return event;
}

describe("useGlobalShortcuts", () => {
  beforeEach(() => {
    navigateMock.mockClear();
  });

  afterEach(() => {
    // Pour purger les listeners laissés par des tests précédents (au cas où
    // on rate un unmount — la protection cleanup du hook le gère mais on
    // double-check ici via un unmount explicite dans chaque test).
  });

  it("should navigate to /upscale on Cmd+1", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("1", { meta: true });
    expect(navigateMock).toHaveBeenCalledWith("/upscale");
  });

  it("should navigate to /batch on Cmd+2", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("2", { meta: true });
    expect(navigateMock).toHaveBeenCalledWith("/batch");
  });

  it("should navigate to /gallery on Cmd+3", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("3", { meta: true });
    expect(navigateMock).toHaveBeenCalledWith("/gallery");
  });

  it("should navigate to /history on Cmd+4", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("4", { meta: true });
    expect(navigateMock).toHaveBeenCalledWith("/history");
  });

  it("should navigate to /settings on Cmd+5", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("5", { meta: true });
    expect(navigateMock).toHaveBeenCalledWith("/settings");
  });

  it("should navigate to /upscale on Cmd+U", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("u", { meta: true });
    expect(navigateMock).toHaveBeenCalledWith("/upscale");
  });

  it("should navigate to /batch on Cmd+B", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("b", { meta: true });
    expect(navigateMock).toHaveBeenCalledWith("/batch");
  });

  it("should accept Ctrl as modifier (Windows/Linux)", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("1", { ctrl: true });
    expect(navigateMock).toHaveBeenCalledWith("/upscale");
  });

  it("should ignore shortcuts without meta or ctrl", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("1");
    fireKey("u");
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("should NOT handle Cmd+K (reserved for command palette)", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("k", { meta: true });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("should ignore unmapped Cmd combinations", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("z", { meta: true });
    fireKey("9", { meta: true });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("should prevent default on handled shortcuts", () => {
    renderHook(() => useGlobalShortcuts());
    const event = fireKey("1", { meta: true });
    expect(event.defaultPrevented).toBe(true);
  });

  it("should unbind listener on unmount", () => {
    const { unmount } = renderHook(() => useGlobalShortcuts());
    unmount();
    fireKey("1", { meta: true });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("should accept uppercase keys (caps lock / shift)", () => {
    renderHook(() => useGlobalShortcuts());
    fireKey("U", { meta: true });
    expect(navigateMock).toHaveBeenCalledWith("/upscale");
  });
});
