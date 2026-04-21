/**
 * Hook React qui polle les ressources système toutes les 15s via Tauri
 * et expose le verdict de capacité (local vs cloud).
 *
 * Retourne `null` en contexte non-Tauri (dev web) — le composant appelant
 * doit alors considérer `can_run_local = false` par défaut (fallback cloud).
 */

import { useEffect, useState } from "react";

import {
  canRunLocalStrict,
  type CapabilityDecision,
  type SystemResources,
} from "@/lib/capability";

/** Intervalle de rafraîchissement du snapshot (ms). */
const REFRESH_INTERVAL_MS = 15_000;

/**
 * Hook principal — retourne le verdict courant + une fonction pour forcer
 * un refresh manuel (ex. avant chaque soumission de job).
 */
export function useSystemResources(): {
  decision: CapabilityDecision | null;
  refresh: () => Promise<CapabilityDecision | null>;
  error: string | null;
} {
  const [decision, setDecision] = useState<CapabilityDecision | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchOnce = async (): Promise<CapabilityDecision | null> => {
    // `invoke` n'est disponible qu'en contexte Tauri ; en dev web Vite
    // l'import dynamique échoue ou `invoke` renvoie une erreur, auquel
    // cas on retourne `null` et le composant tombe en fallback cloud.
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const snap = await invoke<SystemResources>("get_system_resources");
      const verdict = canRunLocalStrict(snap);
      setDecision(verdict);
      setError(null);
      return verdict;
    } catch (exc) {
      // Hors Tauri (mode web dev) : on ne log pas en erreur, c'est
      // attendu. L'UI doit afficher "mode cloud" par défaut.
      const message = exc instanceof Error ? exc.message : String(exc);
      setError(message);
      setDecision(null);
      return null;
    }
  };

  useEffect(() => {
    void fetchOnce();
    const interval = setInterval(() => {
      void fetchOnce();
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  return { decision, refresh: fetchOnce, error };
}
