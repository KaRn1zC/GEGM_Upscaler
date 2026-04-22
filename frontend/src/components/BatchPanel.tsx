import { useCallback, useImperativeHandle, useState, type Ref } from "react";
import { m, AnimatePresence, Reorder } from "motion/react";
import { useDropzone } from "react-dropzone";
import { Upload, X, Play, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ACCEPTED_IMAGE_TYPES,
  MAX_FILE_SIZE_BYTES,
  SCALE_FACTORS,
  type ScaleFactor,
} from "@/lib/constants";

/**
 * API impérative exposée par `BatchPanel` via ref.
 *
 * Permet au parent d'injecter des fichiers dans la queue sans passer par un
 * flux de props (utilisé pour le drag-drop natif Tauri qui arrive au niveau
 * fenêtre).
 */
export interface BatchPanelHandle {
  addFiles: (files: File[]) => void;
}

interface BatchPanelProps {
  onSubmit: (files: File[], scaleFactor: ScaleFactor) => Promise<void>;
  isSubmitting: boolean;
  ref?: Ref<BatchPanelHandle>;
}

interface QueuedFile {
  id: string;
  file: File;
  previewUrl: string;
}

export function BatchPanel({ onSubmit, isSubmitting, ref }: BatchPanelProps) {
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [scaleFactor, setScaleFactor] = useState<ScaleFactor>(4);

  const onDrop = useCallback((accepted: File[]) => {
    const newItems: QueuedFile[] = accepted.map((file) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${Math.random()}`,
      file,
      previewUrl: URL.createObjectURL(file),
    }));
    setQueue((q) => [...q, ...newItems]);
  }, []);

  // Expose une API impérative (`addFiles`) au parent — alimente la même
  // queue que le drag-drop HTML5 interne. Consommée par `useTauriDragDrop`
  // dans `BatchPage`.
  useImperativeHandle(ref, () => ({ addFiles: onDrop }), [onDrop]);

  const removeItem = useCallback((id: string) => {
    setQueue((q) => {
      const item = q.find((i) => i.id === id);
      if (item) URL.revokeObjectURL(item.previewUrl);
      return q.filter((i) => i.id !== id);
    });
  }, []);

  const clearQueue = useCallback(() => {
    queue.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    setQueue([]);
  }, [queue]);

  const handleSubmit = useCallback(async () => {
    if (queue.length === 0) return;
    const files = queue.map((q) => q.file);
    await onSubmit(files, scaleFactor);
    clearQueue();
  }, [queue, scaleFactor, onSubmit, clearQueue]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_IMAGE_TYPES,
    maxSize: MAX_FILE_SIZE_BYTES,
    multiple: true,
    disabled: isSubmitting,
  });

  const totalSize = queue.reduce((sum, item) => sum + item.file.size, 0);
  const formatSize = (bytes: number) =>
    bytes > 1024 * 1024
      ? `${(bytes / 1024 / 1024).toFixed(1)} Mo`
      : `${(bytes / 1024).toFixed(0)} Ko`;

  return (
    <div className="space-y-5">
      {/* Dropzone */}
      <m.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      >
        <div
          {...getRootProps()}
          className={cn(
            "relative rounded-2xl border-2 border-dashed cursor-pointer overflow-hidden transition-all duration-500",
            isDragActive
              ? "border-primary bg-primary/5 glow-md"
              : "border-border/70 hover:border-border magnetic-pulse",
            isSubmitting && "opacity-50 cursor-not-allowed pointer-events-none",
          )}
        >
          <input {...getInputProps()} />

          {/* Grille diagonale subtile */}
          <div
            className="absolute inset-0 opacity-[0.04] pointer-events-none"
            style={{
              backgroundImage:
                "linear-gradient(45deg, transparent 48%, #1436de 49%, #1436de 51%, transparent 52%)",
              backgroundSize: "28px 28px",
            }}
          />

          <div className="relative flex flex-col items-center justify-center py-14 px-6">
            <m.div
              animate={
                isDragActive
                  ? { scale: [1, 1.08, 1], rotate: [0, 2, -2, 0] }
                  : { scale: 1, rotate: 0 }
              }
              transition={{
                duration: 1.6,
                repeat: isDragActive ? Infinity : 0,
                ease: "easeInOut",
              }}
              className={cn(
                "w-14 h-14 rounded-2xl flex items-center justify-center mb-5 transition-colors duration-300",
                isDragActive
                  ? "bg-primary/20 text-primary glow-pulse"
                  : "bg-card border border-border text-muted-foreground",
              )}
            >
              <Upload className="w-6 h-6" strokeWidth={1.5} />
            </m.div>
            <p className="font-display font-light text-xl lg:text-2xl text-foreground text-center leading-tight">
              {isDragActive
                ? "Déposer les images"
                : "Glisser plusieurs images"}
            </p>
            <p className="mt-2.5 text-[10px] uppercase tracking-[0.22em] text-muted-foreground font-sans text-center">
              Sélection multiple · Traitement parallèle
            </p>
          </div>
        </div>
      </m.div>

      {/* Paramètres batch */}
      <AnimatePresence>
        {queue.length > 0 && (
          <m.div
            initial={{ opacity: 0, y: -8, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -8, height: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 26 }}
            className="overflow-hidden"
          >
            <div className="flex items-center justify-between gap-3 p-4 rounded-xl border border-border bg-card flex-wrap">
              <div className="flex items-center gap-3 min-w-0">
                <span
                  data-tabular
                  className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground"
                >
                  <span className="text-primary font-semibold">
                    {queue.length}
                  </span>{" "}
                  image{queue.length > 1 ? "s" : ""}
                  <span className="mx-1.5 opacity-40">·</span>
                  {formatSize(totalSize)}
                </span>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                {/* Sélecteur de facteur avec indicateur glissant */}
                <div className="relative flex items-center gap-1 bg-muted rounded-lg p-0.5">
                  {SCALE_FACTORS.map((f) => (
                    <m.button
                      key={f}
                      onClick={() => setScaleFactor(f)}
                      disabled={isSubmitting}
                      whileTap={{ scale: 0.93 }}
                      className="relative z-10 text-xs px-4 py-1.5 rounded-md font-semibold font-mono"
                    >
                      {scaleFactor === f && (
                        <m.div
                          layoutId="batch-scale-indicator"
                          className="absolute inset-0 bg-primary rounded-md glow-sm"
                          transition={{
                            type: "spring",
                            stiffness: 400,
                            damping: 30,
                          }}
                        />
                      )}
                      <span
                        data-tabular
                        className={cn(
                          "relative",
                          scaleFactor === f
                            ? "text-primary-foreground"
                            : "text-muted-foreground",
                        )}
                      >
                        {f}×
                      </span>
                    </m.button>
                  ))}
                </div>

                <m.button
                  onClick={clearQueue}
                  disabled={isSubmitting}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.96 }}
                  transition={{ type: "spring", stiffness: 400, damping: 25 }}
                  className="text-[11px] font-medium px-3 py-2 rounded-lg bg-muted text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
                >
                  Vider
                </m.button>

                <m.button
                  onClick={handleSubmit}
                  disabled={isSubmitting}
                  whileHover={!isSubmitting ? { scale: 1.03, y: -1 } : {}}
                  whileTap={!isSubmitting ? { scale: 0.96 } : {}}
                  transition={{ type: "spring", stiffness: 400, damping: 25 }}
                  className="text-[11px] font-medium px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:glow-md transition-shadow flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Envoi...
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5" strokeWidth={2.5} />
                      Lancer le batch
                    </>
                  )}
                </m.button>
              </div>
            </div>
          </m.div>
        )}
      </AnimatePresence>

      {/* Grille de previews avec reorder drag */}
      {queue.length > 0 && (
        <Reorder.Group
          axis="y"
          values={queue}
          onReorder={setQueue}
          className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3"
          as="div"
        >
          <AnimatePresence>
            {queue.map((item) => (
              <Reorder.Item
                key={item.id}
                value={item}
                as="div"
                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.85, y: -10 }}
                transition={{ type: "spring", stiffness: 280, damping: 26 }}
                whileHover={{ y: -3 }}
                whileDrag={{ scale: 1.05, zIndex: 50 }}
                className="relative group rounded-lg overflow-hidden border border-border bg-card aspect-square cursor-grab active:cursor-grabbing"
              >
                <img
                  src={item.previewUrl}
                  alt={item.file.name}
                  className="w-full h-full object-cover"
                />

                {/* Overlay gradient */}
                <div className="absolute inset-0 bg-gradient-to-t from-black via-black/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

                {/* Bordure intérieure au hover */}
                <div className="absolute inset-0 rounded-lg ring-1 ring-inset ring-primary/0 group-hover:ring-primary/40 transition-all duration-500 pointer-events-none" />

                {/* Bouton close */}
                <m.button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeItem(item.id);
                  }}
                  disabled={isSubmitting}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  className="absolute top-2 right-2 p-1 rounded-md bg-black/70 text-white hover:bg-destructive backdrop-blur-sm transition-colors opacity-0 group-hover:opacity-100"
                >
                  <X className="w-3 h-3" />
                </m.button>

                {/* Nom du fichier */}
                <p className="absolute bottom-2 left-2 right-2 text-[9px] font-mono uppercase tracking-wider text-white/95 truncate opacity-0 group-hover:opacity-100 transition-opacity">
                  {item.file.name}
                </p>
              </Reorder.Item>
            ))}
          </AnimatePresence>
        </Reorder.Group>
      )}
    </div>
  );
}
