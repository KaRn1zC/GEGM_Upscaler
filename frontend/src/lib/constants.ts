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

// Aligné sur la limite backend MAX_UPLOAD_SIZE_MB (300 Mo par défaut) —
// couvre les TIFF de photo shoot plein format. Les deux valeurs doivent
// évoluer ensemble, sinon le backend renvoie un 413 que l'UI n'anticipe pas.
export const MAX_FILE_SIZE_MB = 300;
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

export const SCALE_FACTORS = [2, 4] as const;
export type ScaleFactor = (typeof SCALE_FACTORS)[number];

/**
 * Mapping ``scale_factor → modèle SR`` — **source de vérité** côté UI
 * pour l'affichage uniquement. Le backend applique le même mapping pour
 * la création de job (cf. ``backend/app/jobs/service._model_for_scale``).
 *
 * Chaque scale a son modèle pré-entraîné dédié (pas de fallback, pas de
 * downscale) :
 *   - x4 → DRCT-L (poids officiels ming053l/DRCT, state-of-the-art)
 *   - x2 → HAT-L  (poids officiels XPixelGroup/HAT ; DRCT-L x2 non publié)
 *
 * Le client n'envoie plus ``model_name`` dans ``POST /api/jobs`` — le
 * backend ignore ce champ et le déduit de ``scale_factor``.
 */
export const SCALE_TO_MODEL: Record<ScaleFactor, { name: string; label: string }> = {
  2: { name: "hat-l", label: "HAT-L" },
  4: { name: "drct-l", label: "DRCT-L" },
};

export const JOB_STATUS_LABELS: Record<string, string> = {
  pending: "En attente",
  queued: "En file",
  processing: "En cours",
  completed: "Terminé",
  failed: "Échoué",
  cancelled: "Annulé",
};
