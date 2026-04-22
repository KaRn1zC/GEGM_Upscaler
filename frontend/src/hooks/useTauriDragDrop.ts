import { useEffect } from "react";
import { isTauri, readFileFromPath } from "@/lib/tauri";

// Référence stable partagée entre tous les appelants — évite de créer une
// nouvelle array à chaque render, ce qui invaliderait inutilement le
// tableau de dépendances du useEffect et abonnerait des listeners en
// doublon à chaque re-render du composant parent.
const DEFAULT_ACCEPT: readonly string[] = [
  "png",
  "jpg",
  "jpeg",
  "webp",
  "tif",
  "tiff",
];

/**
 * Écoute les événements natifs drag-drop de la fenêtre Tauri et transmet
 * les fichiers droppés au callback fourni.
 *
 * En contexte Tauri, le webview intercepte les drag-drop OS avant
 * `react-dropzone` — les chemins arrivent via `onDragDropEvent`. On les lit
 * en mémoire via `plugin-fs` et on reconstitue des objets `File` natifs
 * pour rester compatible avec le pipeline d'upload existant.
 *
 * No-op hors runtime Tauri.
 *
 * Args:
 *     onFilesDropped: callback invoqué à chaque drop, reçoit la liste des
 *         `File` reconstitués. Doit être stable (wrap dans `useCallback`
 *         côté appelant) pour éviter de ré-abonner à chaque render.
 *     accept: extensions autorisées (sans le point), minuscules. Les
 *         fichiers hors de cette liste sont silencieusement ignorés.
 *         Si on passe une valeur custom, elle **doit** être stable en
 *         référence (module-level const ou wrap dans `useMemo`).
 */
export function useTauriDragDrop(
  onFilesDropped: (files: File[]) => void,
  accept: readonly string[] = DEFAULT_ACCEPT,
): void {
  useEffect(() => {
    if (!isTauri()) return;

    let unlisten: (() => void) | null = null;
    let cancelled = false;

    void (async () => {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      const dispose = await getCurrentWindow().onDragDropEvent((event) => {
        if (event.payload.type !== "drop") return;

        const paths = event.payload.paths.filter((p) => {
          const ext = p.toLowerCase().split(".").pop() ?? "";
          return accept.includes(ext);
        });

        if (paths.length === 0) return;

        void Promise.all(paths.map((p) => readFileFromPath(p)))
          .then((files) => {
            const valid = files.filter((f): f is File => f !== null);
            if (valid.length > 0) {
              onFilesDropped(valid);
            }
          })
          .catch(() => {
            // Lecture échouée — on log silencieux plutôt que faire planter
            // l'UI, l'utilisateur peut toujours retenter via le bouton
            // Parcourir ou le drop HTML5 classique.
          });
      });

      if (cancelled) {
        dispose();
      } else {
        unlisten = dispose;
      }
    })();

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [onFilesDropped, accept]);
}
