import { useCallback, useEffect, useState } from "react";
import type { ScaleFactor } from "@/lib/constants";

const STORAGE_KEY = "gegm-upscaler-prefs";

export interface UserPreferences {
  defaultScaleFactor: ScaleFactor;
  apiBaseUrl: string;
}

const DEFAULT_PREFERENCES: UserPreferences = {
  defaultScaleFactor: 4,
  apiBaseUrl: "/api",
};

function loadPreferences(): UserPreferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFERENCES;
    const parsed = JSON.parse(raw) as Partial<UserPreferences>;
    return { ...DEFAULT_PREFERENCES, ...parsed };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function usePreferences() {
  const [preferences, setPreferences] = useState<UserPreferences>(loadPreferences);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      // localStorage indisponible (ex : mode privé), ignorer silencieusement.
    }
  }, [preferences]);

  const updatePreference = useCallback(
    <K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => {
      setPreferences((p) => ({ ...p, [key]: value }));
    },
    [],
  );

  const resetPreferences = useCallback(() => {
    setPreferences(DEFAULT_PREFERENCES);
  }, []);

  return { preferences, updatePreference, resetPreferences };
}
