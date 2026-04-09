import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

/**
 * Active les raccourcis clavier globaux pour la navigation entre pages.
 *
 * Mappings :
 * - ⌘1..⌘5 / Ctrl+1..Ctrl+5 → Upscaler / Batch / Galerie / Historique / Paramètres
 * - ⌘U / Ctrl+U → Upscaler (nouvel upscale)
 * - ⌘B / Ctrl+B → Batch (nouveau batch)
 *
 * ⌘K est géré séparément par la palette de commandes (`CommandPalette`)
 * pour éviter le double-binding.
 */
export function useGlobalShortcuts(): void {
  const navigate = useNavigate();

  useEffect(() => {
    const routes: Record<string, string> = {
      "1": "/upscale",
      "2": "/batch",
      "3": "/gallery",
      "4": "/history",
      "5": "/settings",
      u: "/upscale",
      b: "/batch",
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      // Ignore si la Command Palette gère déjà l'événement.
      if (e.key === "k") return;

      const path = routes[e.key.toLowerCase()];
      if (path) {
        e.preventDefault();
        navigate(path);
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [navigate]);
}
