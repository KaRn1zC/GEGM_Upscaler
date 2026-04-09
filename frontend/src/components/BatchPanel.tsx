import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, Play, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ACCEPTED_IMAGE_TYPES,
  MAX_FILE_SIZE_BYTES,
  SCALE_FACTORS,
  type ScaleFactor,
} from "@/lib/constants";

interface BatchPanelProps {
  onSubmit: (files: File[], scaleFactor: ScaleFactor) => Promise<void>;
  isSubmitting: boolean;
}

interface QueuedFile {
  id: string;
  file: File;
  previewUrl: string;
}

export function BatchPanel({ onSubmit, isSubmitting }: BatchPanelProps) {
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
    <div className="space-y-4">
      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={cn(
          "relative rounded-xl border-2 border-dashed transition-all duration-300 cursor-pointer",
          "bg-[repeating-linear-gradient(45deg,transparent,transparent_10px,rgba(99,102,241,0.02)_10px,rgba(99,102,241,0.02)_20px)]",
          isDragActive
            ? "border-primary bg-primary/5 shadow-[0_0_30px_rgba(99,102,241,0.15)]"
            : "border-border/60 hover:border-border hover:bg-muted/30",
          isSubmitting && "opacity-50 cursor-not-allowed",
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center justify-center py-10 px-6">
          <div
            className={cn(
              "w-12 h-12 rounded-2xl flex items-center justify-center mb-4 transition-all duration-300",
              isDragActive
                ? "bg-primary/15 text-primary scale-110"
                : "bg-muted text-muted-foreground",
            )}
          >
            <Upload className="w-5 h-5" />
          </div>
          <p className="text-sm font-medium text-foreground mb-1">
            {isDragActive
              ? "Déposer les images"
              : "Glisser plusieurs images ou cliquer pour parcourir"}
          </p>
          <p className="text-xs text-muted-foreground">
            Sélection multiple — toutes les images seront traitées en parallèle
          </p>
        </div>
      </div>

      {/* Paramètres batch */}
      {queue.length > 0 && (
        <div className="flex items-center justify-between gap-3 p-3 rounded-xl border border-border bg-card">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-xs font-mono text-muted-foreground">
              {queue.length} image{queue.length > 1 ? "s" : ""}
              <span className="mx-1.5 opacity-40">·</span>
              {formatSize(totalSize)}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
              {SCALE_FACTORS.map((f) => (
                <button
                  key={f}
                  onClick={() => setScaleFactor(f)}
                  disabled={isSubmitting}
                  className={cn(
                    "text-xs px-3 py-1.5 rounded-md font-medium transition-all",
                    scaleFactor === f
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {f}&times;
                </button>
              ))}
            </div>

            <button
              onClick={clearQueue}
              disabled={isSubmitting}
              className="text-xs px-3 py-2 rounded-lg bg-muted text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
            >
              Vider
            </button>

            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="text-xs px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Envoi...
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  Lancer le batch
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Grille de previews */}
      {queue.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {queue.map((item) => (
            <div
              key={item.id}
              className="relative group rounded-lg overflow-hidden border border-border bg-card aspect-square"
            >
              <img
                src={item.previewUrl}
                alt={item.file.name}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={() => removeItem(item.id)}
                  disabled={isSubmitting}
                  className="absolute top-1.5 right-1.5 p-1 rounded-md bg-black/60 text-white hover:bg-destructive transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
                <p className="absolute bottom-1.5 left-1.5 right-1.5 text-[10px] font-mono text-white/90 truncate">
                  {item.file.name}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
