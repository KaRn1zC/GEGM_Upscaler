/**
 * Préfixe base des appels API.
 *
 * - **Dev web (Vite seul)** : `/api` (relatif). Vite proxy `/api/*` vers
 *   `localhost:8000` via `vite.config.ts`.
 * - **Prod web (served par FastAPI + StaticFiles)** : `/api` relatif aussi,
 *   car le frontend est servi depuis la même origine que l'API.
 * - **Tauri desktop (.dmg installé)** : `tauri://localhost/api/*` ne pointe
 *   sur rien → il faut une URL absolue vers le backend distant. Le build
 *   release Tauri doit être généré avec `VITE_API_BASE=https://upscaler.gegmgroup.com/api`.
 *
 * La variable est lue au build-time par Vite (pas de runtime-switching).
 */
export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export const ACCEPTED_IMAGE_TYPES: Record<string, string[]> = {
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/webp": [".webp"],
  "image/tiff": [".tiff", ".tif"],
};

export const MAX_FILE_SIZE_MB = 200;
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

export const SCALE_FACTORS = [2, 4] as const;
export type ScaleFactor = (typeof SCALE_FACTORS)[number];

export const MODEL_OPTIONS = [
  { value: "drct-l", label: "DRCT-L (recommandé)" },
  { value: "hat-l", label: "HAT-L (fallback)" },
] as const;

export const JOB_STATUS_LABELS: Record<string, string> = {
  pending: "En attente",
  queued: "En file",
  processing: "En cours",
  completed: "Terminé",
  failed: "Échoué",
  cancelled: "Annulé",
};
