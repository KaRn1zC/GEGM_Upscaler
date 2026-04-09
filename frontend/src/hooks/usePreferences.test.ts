import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePreferences } from "./usePreferences";

const STORAGE_KEY = "gegm-upscaler-prefs";

describe("usePreferences", () => {

  it("should return default values on first load", () => {
    const { result } = renderHook(() => usePreferences());

    expect(result.current.preferences.defaultScaleFactor).toBe(4);
    expect(result.current.preferences.defaultModel).toBe("drct-l");
    expect(result.current.preferences.apiBaseUrl).toBe("/api");
  });

  it("should persist preferences to localStorage", () => {
    const { result } = renderHook(() => usePreferences());

    act(() => {
      result.current.updatePreference("defaultScaleFactor", 2);
    });

    expect(result.current.preferences.defaultScaleFactor).toBe(2);

    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(stored.defaultScaleFactor).toBe(2);
  });

  it("should load persisted values on mount", () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ defaultScaleFactor: 2, defaultModel: "hat-l" }),
    );

    const { result } = renderHook(() => usePreferences());

    expect(result.current.preferences.defaultScaleFactor).toBe(2);
    expect(result.current.preferences.defaultModel).toBe("hat-l");
    // Les clés non persistées doivent garder leur valeur par défaut.
    expect(result.current.preferences.apiBaseUrl).toBe("/api");
  });

  it("should reset to defaults", () => {
    const { result } = renderHook(() => usePreferences());

    act(() => {
      result.current.updatePreference("defaultScaleFactor", 2);
      result.current.updatePreference("defaultModel", "hat-l");
    });

    act(() => {
      result.current.resetPreferences();
    });

    expect(result.current.preferences.defaultScaleFactor).toBe(4);
    expect(result.current.preferences.defaultModel).toBe("drct-l");
  });

  it("should fallback to defaults if localStorage contains invalid JSON", () => {
    localStorage.setItem(STORAGE_KEY, "{not-valid-json");

    const { result } = renderHook(() => usePreferences());

    expect(result.current.preferences.defaultScaleFactor).toBe(4);
  });

  it("should update multiple preferences independently", () => {
    const { result } = renderHook(() => usePreferences());

    act(() => {
      result.current.updatePreference("defaultModel", "hat-l");
    });

    expect(result.current.preferences.defaultModel).toBe("hat-l");
    expect(result.current.preferences.defaultScaleFactor).toBe(4);
  });
});
