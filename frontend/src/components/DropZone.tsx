import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, ImageIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { ACCEPTED_IMAGE_TYPES, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from "@/lib/constants";

interface DropZoneProps {
  onFileAccepted: (file: File) => void;
  disabled?: boolean;
}

export function DropZone({ onFileAccepted, disabled = false }: DropZoneProps) {
  const [preview, setPreview] = useState<{ url: string; name: string; size: string } | null>(null);

  const onDrop = useCallback(
    (accepted: File[]) => {
      const file = accepted[0];
      if (!file) return;

      const url = URL.createObjectURL(file);
      const size =
        file.size > 1024 * 1024
          ? `${(file.size / 1024 / 1024).toFixed(1)} Mo`
          : `${(file.size / 1024).toFixed(0)} Ko`;

      setPreview({ url, name: file.name, size });
      onFileAccepted(file);
    },
    [onFileAccepted],
  );

  const clearPreview = useCallback(() => {
    if (preview) {
      URL.revokeObjectURL(preview.url);
      setPreview(null);
    }
  }, [preview]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_IMAGE_TYPES,
    maxSize: MAX_FILE_SIZE_BYTES,
    multiple: false,
    disabled,
  });

  if (preview) {
    return (
      <div className="relative group rounded-xl overflow-hidden border border-border bg-card">
        <img
          src={preview.url}
          alt={preview.name}
          className="w-full h-64 object-contain bg-black/40"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent" />
        <div className="absolute bottom-0 inset-x-0 p-4 flex items-end justify-between">
          <div className="min-w-0">
            <p className="text-sm font-medium text-white truncate">{preview.name}</p>
            <p className="text-xs text-white/60">{preview.size}</p>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              clearPreview();
            }}
            className="shrink-0 ml-3 p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/80 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      {...getRootProps()}
      className={cn(
        "relative rounded-xl border-2 border-dashed transition-all duration-300 cursor-pointer",
        "bg-[repeating-linear-gradient(45deg,transparent,transparent_10px,rgba(99,102,241,0.02)_10px,rgba(99,102,241,0.02)_20px)]",
        isDragActive
          ? "border-primary bg-primary/5 shadow-[0_0_30px_rgba(99,102,241,0.15)]"
          : "border-border/60 hover:border-border hover:bg-muted/30",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <input {...getInputProps()} />

      <div className="flex flex-col items-center justify-center py-16 px-6">
        <div
          className={cn(
            "w-14 h-14 rounded-2xl flex items-center justify-center mb-5 transition-all duration-300",
            isDragActive
              ? "bg-primary/15 text-primary scale-110"
              : "bg-muted text-muted-foreground",
          )}
        >
          {isDragActive ? <ImageIcon className="w-6 h-6" /> : <Upload className="w-6 h-6" />}
        </div>

        <p className="text-sm font-medium text-foreground mb-1">
          {isDragActive ? "Déposer l'image ici" : "Glisser une image ou cliquer pour parcourir"}
        </p>
        <p className="text-xs text-muted-foreground">
          PNG, JPEG, WebP, TIFF — {MAX_FILE_SIZE_MB} Mo max
        </p>
      </div>
    </div>
  );
}
