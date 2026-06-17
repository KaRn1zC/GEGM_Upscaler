import { m } from "motion/react";
import { CheckCircle2, Circle, Download, Trash2, ZoomIn } from "lucide-react";
import { getDownloadUrl, type JobResponse } from "@/lib/api";
import { downloadFile } from "@/lib/tauri";
import { cn } from "@/lib/utils";
import { useConfirm } from "@/hooks/useConfirm";

interface GalleryProps {
  jobs: JobResponse[];
  onZoom?: (job: JobResponse) => void;
  /** Suppression définitive d'un résultat (confirmation demandée ici). */
  onDelete?: (job: JobResponse) => void;
  /** Mode sélection multiple : le clic sur une vignette coche au lieu de zoomer. */
  selectMode?: boolean;
  selectedIds?: Set<string>;
  onToggleSelect?: (id: string) => void;
}

export function Gallery({
  jobs,
  onZoom,
  onDelete,
  selectMode = false,
  selectedIds,
  onToggleSelect,
}: GalleryProps) {
  const confirm = useConfirm();

  const handleDelete = async (job: JobResponse) => {
    if (!onDelete) return;
    const ok = await confirm({
      title: "Supprimer ce résultat ?",
      description:
        "L'image source et le résultat seront définitivement supprimés du stockage. Cette action est irréversible.",
      confirmLabel: "Supprimer",
    });
    if (ok) onDelete(job);
  };

  if (jobs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <p className="text-sm">Aucun résultat à afficher</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
      {jobs.map((job, i) => {
        const isSelected = selectedIds?.has(job.id) ?? false;
        return (
        <m.div
          key={job.id}
          layoutId={`job-card-${job.id}`}
          initial={{ opacity: 0, y: 30, scale: 0.95 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={{
            type: "spring",
            stiffness: 220,
            damping: 24,
            delay: Math.min(i * 0.05, 0.6),
          }}
          whileHover={{ y: -4 }}
          onClick={selectMode ? () => onToggleSelect?.(job.id) : undefined}
          className={cn(
            "group relative rounded-xl overflow-hidden border bg-card",
            "aspect-square transition-colors duration-300 hover:glow-sm",
            selectMode && "cursor-pointer",
            isSelected ? "border-primary glow-sm" : "border-border hover:border-primary/40",
          )}
        >
          <m.img
            layoutId={`job-img-${job.id}`}
            src={getDownloadUrl(job.id)}
            alt={`Job ${job.id}`}
            className={cn(
              "w-full h-full object-cover transition-opacity",
              selectMode && !isSelected && "opacity-70",
            )}
            loading="lazy"
          />

          {/* Overlay gradient */}
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

          {/* Bordure intérieure qui apparaît au hover */}
          <div className="absolute inset-0 rounded-xl ring-1 ring-inset ring-primary/0 group-hover:ring-primary/40 transition-all duration-500 pointer-events-none" />

          {/* Coche de sélection (mode sélection) */}
          {selectMode && (
            <div className="absolute top-2.5 left-2.5 z-10 pointer-events-none">
              {isSelected ? (
                <CheckCircle2
                  className="w-5 h-5 text-primary drop-shadow-[0_1px_3px_rgba(0,0,0,0.8)]"
                  strokeWidth={2}
                />
              ) : (
                <Circle
                  className="w-5 h-5 text-white/80 drop-shadow-[0_1px_3px_rgba(0,0,0,0.8)]"
                  strokeWidth={2}
                />
              )}
            </div>
          )}

          {/* Actions + métadonnées (masquées en mode sélection) */}
          <div
            className={cn(
              "absolute inset-0 transition-opacity duration-300",
              selectMode
                ? "opacity-0 pointer-events-none"
                : "opacity-0 group-hover:opacity-100",
            )}
          >
            {/* Boutons action en haut */}
            <div className="absolute top-2.5 right-2.5 flex gap-1.5">
              {onZoom && (
                <m.button
                  onClick={() => onZoom(job)}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  transition={{ type: "spring", stiffness: 400, damping: 25 }}
                  className="p-1.5 rounded-lg bg-black/70 text-white hover:bg-primary hover:text-primary-foreground backdrop-blur-sm transition-colors"
                  title="Inspecter"
                >
                  <ZoomIn className="w-3.5 h-3.5" strokeWidth={2} />
                </m.button>
              )}
              <m.button
                onClick={() => {
                  const filename = job.output_key
                    ? job.output_key.split("/").pop() ?? "upscaled.jpg"
                    : "upscaled.jpg";
                  void downloadFile(getDownloadUrl(job.id), filename);
                }}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="p-1.5 rounded-lg bg-black/70 text-white hover:bg-primary hover:text-primary-foreground backdrop-blur-sm transition-colors"
                title="Télécharger"
              >
                <Download className="w-3.5 h-3.5" strokeWidth={2} />
              </m.button>
              {onDelete && (
                <m.button
                  onClick={() => void handleDelete(job)}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  transition={{ type: "spring", stiffness: 400, damping: 25 }}
                  className="p-1.5 rounded-lg bg-black/70 text-white hover:bg-destructive backdrop-blur-sm transition-colors"
                  title="Supprimer"
                  aria-label="Supprimer le résultat"
                >
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={2} />
                </m.button>
              )}
            </div>

            {/* Métadonnées en bas */}
            <div className="absolute bottom-2.5 left-2.5 right-2.5">
              <p
                data-tabular
                className="text-[10px] font-mono uppercase tracking-[0.1em] text-white/95"
              >
                {job.output_width}×{job.output_height}
              </p>
              <p className="text-[9px] font-mono uppercase tracking-[0.15em] text-white/55 mt-0.5">
                {job.model_name} · {job.scale_factor}×
              </p>
            </div>
          </div>
        </m.div>
        );
      })}
    </div>
  );
}
