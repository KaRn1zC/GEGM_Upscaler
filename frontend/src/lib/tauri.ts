/**
 * Helpers Tauri — détection du contexte desktop et wrappers typés pour les
 * plugins natifs (notification, dialog, fs).
 *
 * Toutes les fonctions sont des no-op ou renvoient `null` en contexte web
 * classique (Vite seul, hors Tauri). Cela permet d'écrire du code appelant
 * les natives sans guard explicite à chaque site d'appel.
 */

/**
 * Indique si l'application tourne dans un runtime Tauri (vs. navigateur Vite).
 *
 * Tauri 2 injecte `__TAURI_INTERNALS__` sur `window` au bootstrap — c'est le
 * détecteur officiel recommandé.
 */
export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * Dérive un type MIME image depuis l'extension d'un chemin de fichier.
 *
 * Utilisé après `dialog::open` ou drag-drop natif : le chemin nous est donné
 * sans métadonnées, il faut reconstruire le MIME avant de créer un `File`.
 */
export function mimeFromPath(path: string): string {
  const ext = path.toLowerCase().split(".").pop() ?? "";
  switch (ext) {
    case "png":
      return "image/png";
    case "jpg":
    case "jpeg":
      return "image/jpeg";
    case "webp":
      return "image/webp";
    case "tif":
    case "tiff":
      return "image/tiff";
    default:
      return "application/octet-stream";
  }
}

/**
 * Extrait le nom de fichier d'un chemin POSIX ou Windows.
 *
 * `/Users/aboy/pic.png` → `pic.png`, `C:\\imgs\\pic.png` → `pic.png`.
 */
export function basename(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  return normalized.split("/").pop() ?? normalized;
}

/**
 * Lit un fichier depuis son chemin absolu et le transforme en `File` web.
 *
 * No-op (renvoie `null`) en dehors de Tauri. En contexte Tauri, lit les
 * bytes via `plugin-fs` puis emballe dans un `File` compatible avec le
 * reste du code (upload XHR, preview, etc.).
 */
export async function readFileFromPath(path: string): Promise<File | null> {
  if (!isTauri()) return null;
  const { readFile } = await import("@tauri-apps/plugin-fs");
  const bytes = await readFile(path);
  const blob = new Blob([bytes as BlobPart], { type: mimeFromPath(path) });
  return new File([blob], basename(path), { type: blob.type });
}

/**
 * Télécharge un fichier depuis une URL authentifiée.
 *
 * - En contexte Tauri : ouvre un dialog `save` natif pour laisser l'utilisateur
 *   choisir la destination, puis télécharge via ``fetch`` et écrit via
 *   ``plugin-fs``. ``window.open(url, "_blank")`` ne déclenche rien dans le
 *   webview Tauri — c'est le bug qu'on contourne.
 * - En contexte web : crée un ``<a download>`` temporaire et le clique.
 *
 * Args:
 *     url: URL complète, déjà authentifiée (query param ``?token=``).
 *     defaultFilename: nom suggéré pour le fichier côté dialog / attribut
 *         ``download``. Extrait depuis ``job.output_key`` côté appelant.
 */
export async function downloadFile(
  url: string,
  defaultFilename: string,
): Promise<void> {
  if (isTauri()) {
    const { save } = await import("@tauri-apps/plugin-dialog");
    const path = await save({ defaultPath: defaultFilename });
    if (!path) return;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Téléchargement échoué (HTTP ${res.status})`);
    const bytes = new Uint8Array(await res.arrayBuffer());
    const { writeFile } = await import("@tauri-apps/plugin-fs");
    await writeFile(path, bytes);
    return;
  }

  // Flow web standard : <a download> synthétique.
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = defaultFilename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}
