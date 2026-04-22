import { useCallback, useImperativeHandle, useState, type Ref } from "react";
import { m, AnimatePresence } from "motion/react";
import { useDropzone } from "react-dropzone";
import { Upload, X, ImageIcon, FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ACCEPTED_IMAGE_TYPES,
  MAX_FILE_SIZE_BYTES,
  MAX_FILE_SIZE_MB,
} from "@/lib/constants";
import { isTauri, readFileFromPath } from "@/lib/tauri";

/**
 * API impérative exposée par `DropZone` via ref.
 *
 * `acceptFile` : injecte un fichier comme si l'utilisateur l'avait glissé ou
 * sélectionné via Parcourir (preview + callback `onFileAccepted`). Utilisé
 * par le drag-drop natif Tauri qui arrive au niveau fenêtre.
 *
 * `clear` : remet la DropZone à son état vide (utile quand le parent vient
 * de lancer l'upscale et veut libérer la zone pour une nouvelle sélection).
 */
export interface DropZoneHandle {
  acceptFile: (file: File) => void;
  clear: () => void;
}

interface DropZoneProps {
  onFileAccepted: (file: File) => void;
  /**
   * Appelé quand l'utilisateur retire manuellement l'image via le bouton X.
   * Permet au parent de rester synchronisé (ex. clear d'un `pendingFile`
   * en attente de lancement).
   */
  onFileCleared?: () => void;
  disabled?: boolean;
  ref?: Ref<DropZoneHandle>;
}

interface PreviewState {
  url: string;
  name: string;
  size: string;
  megapixels?: number;
}

export function DropZone({
  onFileAccepted,
  onFileCleared,
  disabled = false,
  ref,
}: DropZoneProps) {
  const [preview, setPreview] = useState<PreviewState | null>(null);

  const onDrop = useCallback(
    (accepted: File[]) => {
      const file = accepted[0];
      if (!file) return;

      const url = URL.createObjectURL(file);
      const size =
        file.size > 1024 * 1024
          ? `${(file.size / 1024 / 1024).toFixed(1)} Mo`
          : `${(file.size / 1024).toFixed(0)} Ko`;

      // Lecture asynchrone des dimensions pour calculer les mégapixels réels.
      const img = new Image();
      img.onload = () => {
        const mp = (img.width * img.height) / 1_000_000;
        setPreview({ url, name: file.name, size, megapixels: mp });
      };
      img.src = url;
      setPreview({ url, name: file.name, size });
      onFileAccepted(file);
    },
    [onFileAccepted],
  );

  const clearPreview = useCallback(() => {
    if (preview) {
      URL.revokeObjectURL(preview.url);
      setPreview(null);
      onFileCleared?.();
    }
  }, [preview, onFileCleared]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_IMAGE_TYPES,
    maxSize: MAX_FILE_SIZE_BYTES,
    multiple: false,
    disabled,
  });

  // Expose une API impérative pour que le parent puisse injecter un fichier
  // (drag-drop natif Tauri) ou forcer un reset visuel après lancement de
  // l'upscale.
  useImperativeHandle(
    ref,
    () => ({
      acceptFile: (file: File) => onDrop([file]),
      clear: clearPreview,
    }),
    [onDrop, clearPreview],
  );

  // Ouvre le dialog natif macOS via le plugin Tauri. Les types acceptés
  // matchent ACCEPTED_IMAGE_TYPES (PNG, JPEG, WebP, TIFF). Le bouton est
  // masqué hors contexte Tauri — en mode web, l'input invisible de
  // react-dropzone suffit.
  const handleBrowseNative = useCallback(async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({
      multiple: false,
      directory: false,
      filters: [
        { name: "Images", extensions: ["png", "jpg", "jpeg", "webp", "tif", "tiff"] },
      ],
    });
    if (typeof selected !== "string") return;
    const file = await readFileFromPath(selected);
    if (file) onDrop([file]);
  }, [onDrop]);

  const showBrowseButton = isTauri();

  return (
    <AnimatePresence mode="wait" initial={false}>
      {preview ? (
        <m.div
          key="preview"
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: -10 }}
          transition={{ type: "spring", stiffness: 260, damping: 24 }}
          className="relative rounded-2xl overflow-hidden border border-border bg-card group"
        >
          <img
            src={preview.url}
            alt={preview.name}
            className="w-full h-80 object-contain bg-[#040406]"
          />

          {/* Dégradé bas pour contraste du texte */}
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/30 to-transparent pointer-events-none" />

          {/* Bordure intérieure fine bleu électrique au hover */}
          <div className="absolute inset-0 rounded-2xl ring-1 ring-inset ring-primary/0 group-hover:ring-primary/40 transition-all duration-500 pointer-events-none" />

          {/* Métadonnées + bouton close */}
          <div className="absolute bottom-0 inset-x-0 p-5 flex items-end justify-between gap-4">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground truncate">
                {preview.name}
              </p>
              <div className="mt-1.5 flex items-center gap-2.5 text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground">
                <span data-tabular>{preview.size}</span>
                {preview.megapixels !== undefined && (
                  <>
                    <span className="text-primary/50">·</span>
                    <m.span
                      data-tabular
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ type: "spring", stiffness: 300, damping: 24 }}
                      className="text-primary"
                    >
                      {preview.megapixels.toFixed(1)} MP
                    </m.span>
                  </>
                )}
              </div>
            </div>

            <m.button
              onClick={(e) => {
                e.stopPropagation();
                clearPreview();
              }}
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.92 }}
              className="shrink-0 p-2 rounded-lg bg-white/10 hover:bg-destructive text-white/80 hover:text-white backdrop-blur-sm transition-colors"
              aria-label="Retirer l'image"
            >
              <X className="w-4 h-4" />
            </m.button>
          </div>
        </m.div>
      ) : (
        <m.div
          key="dropzone"
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.98 }}
          transition={{ type: "spring", stiffness: 280, damping: 26 }}
        >
          <div
            {...getRootProps()}
            className={cn(
              "relative rounded-2xl border-2 border-dashed cursor-pointer overflow-hidden",
              "transition-all duration-500",
              isDragActive
                ? "border-primary bg-primary/5 glow-md"
                : "border-border/70 hover:border-border magnetic-pulse",
              disabled && "opacity-50 cursor-not-allowed pointer-events-none",
            )}
          >
            <input {...getInputProps()} />

            {/* Grille diagonale subtile en arrière-plan — signature tech */}
            <div
              className="absolute inset-0 opacity-[0.04] pointer-events-none"
              style={{
                backgroundImage:
                  "linear-gradient(45deg, transparent 48%, #1436de 49%, #1436de 51%, transparent 52%)",
                backgroundSize: "28px 28px",
              }}
            />

            <div className="relative flex flex-col items-center justify-center py-24 px-6">
              <m.div
                animate={
                  isDragActive
                    ? {
                        scale: [1, 1.08, 1],
                        rotate: [0, 2, -2, 0],
                      }
                    : { scale: 1, rotate: 0 }
                }
                transition={{
                  duration: 1.6,
                  repeat: isDragActive ? Infinity : 0,
                  ease: "easeInOut",
                }}
                className={cn(
                  "w-16 h-16 rounded-2xl flex items-center justify-center mb-7 transition-colors duration-300",
                  isDragActive
                    ? "bg-primary/20 text-primary glow-pulse"
                    : "bg-card border border-border text-muted-foreground",
                )}
              >
                {isDragActive ? (
                  <ImageIcon className="w-7 h-7" strokeWidth={1.5} />
                ) : (
                  <Upload className="w-7 h-7" strokeWidth={1.5} />
                )}
              </m.div>

              <p className="font-display font-light text-2xl lg:text-3xl text-foreground text-center leading-tight">
                {isDragActive ? "Déposer l'image" : "Glisser une image"}
              </p>
              <p className="mt-3 text-[10px] uppercase tracking-[0.22em] text-muted-foreground font-sans">
                PNG · JPEG · WebP · TIFF · max {MAX_FILE_SIZE_MB} Mo
              </p>

              {showBrowseButton && (
                <m.button
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleBrowseNative();
                  }}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  disabled={disabled}
                  className="mt-6 inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border/70 bg-card/60 backdrop-blur-sm text-[11px] uppercase tracking-[0.2em] text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors font-sans"
                >
                  <FolderOpen className="w-3.5 h-3.5" strokeWidth={1.8} />
                  Parcourir
                </m.button>
              )}
            </div>
          </div>
        </m.div>
      )}
    </AnimatePresence>
  );
}
