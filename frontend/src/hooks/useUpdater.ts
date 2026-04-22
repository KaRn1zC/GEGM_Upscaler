import { useEffect, useRef } from "react";
import { useUpdaterStore } from "@/stores/useUpdaterStore";

/**
 * Hook de commodité : déclenche un check de MAJ au premier mount (idempotent
 * via ``checkedOnce``) et expose l'état courant du store updater.
 *
 * Utilisé par `UpdateBanner` pour afficher la notification globale, et par
 * `SettingsPage` pour le bouton de check manuel. Les deux partagent le
 * même store Zustand → le résultat d'un check dans Settings fait aussi
 * apparaître la bannière.
 */
export function useUpdater() {
  const state = useUpdaterStore();
  const triggeredRef = useRef(false);

  useEffect(() => {
    if (triggeredRef.current) return;
    triggeredRef.current = true;
    if (!state.checkedOnce) {
      void state.checkNow();
    }
  }, [state]);

  return state;
}
