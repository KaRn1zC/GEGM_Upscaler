import { m } from "motion/react";
import { Download, ZoomIn } from "lucide-react";
import type { JobResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface GalleryProps {
  jobs: JobResponse[];
  onZoom?: (job: JobResponse) => void;
}

export function Gallery({ jobs, onZoom }: GalleryProps) {
  if (jobs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <p className="text-sm">Aucun résultat à afficher</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
      {jobs.map((job, i) => (
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
          className={cn(
            "group relative rounded-xl overflow-hidden border border-border bg-card",
            "aspect-square transition-colors duration-300 hover:border-primary/40",
            "hover:glow-sm",
          )}
        >
          <m.img
            layoutId={`job-img-${job.id}`}
            src={`/api/jobs/${job.id}/download`}
            alt={`Job ${job.id}`}
            className="w-full h-full object-cover"
            loading="lazy"
          />

          {/* Overlay gradient */}
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

          {/* Bordure intérieure qui apparaît au hover */}
          <div className="absolute inset-0 rounded-xl ring-1 ring-inset ring-primary/0 group-hover:ring-primary/40 transition-all duration-500 pointer-events-none" />

          {/* Actions + métadonnées */}
          <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
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
                onClick={() =>
                  window.open(`/api/jobs/${job.id}/download`, "_blank")
                }
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="p-1.5 rounded-lg bg-black/70 text-white hover:bg-primary hover:text-primary-foreground backdrop-blur-sm transition-colors"
                title="Télécharger"
              >
                <Download className="w-3.5 h-3.5" strokeWidth={2} />
              </m.button>
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
      ))}
    </div>
  );
}
