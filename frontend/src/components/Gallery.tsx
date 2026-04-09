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
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <p className="text-sm">Aucun résultat à afficher</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
      {jobs.map((job) => (
        <div
          key={job.id}
          className={cn(
            "group relative rounded-xl overflow-hidden border border-border bg-card",
            "aspect-square transition-all duration-200 hover:border-primary/30",
            "hover:shadow-[0_0_30px_rgba(99,102,241,0.08)]",
          )}
        >
          <img
            src={`/api/jobs/${job.id}/download`}
            alt={`Job ${job.id}`}
            className="w-full h-full object-cover"
            loading="lazy"
          />

          {/* Overlay actions */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
            <div className="absolute top-2 right-2 flex gap-1.5">
              {onZoom && (
                <button
                  onClick={() => onZoom(job)}
                  className="p-1.5 rounded-lg bg-black/60 text-white hover:bg-primary/80 backdrop-blur-sm transition-colors"
                  title="Inspecter"
                >
                  <ZoomIn className="w-3.5 h-3.5" />
                </button>
              )}
              <button
                onClick={() =>
                  window.open(`/api/jobs/${job.id}/download`, "_blank")
                }
                className="p-1.5 rounded-lg bg-black/60 text-white hover:bg-primary/80 backdrop-blur-sm transition-colors"
                title="Télécharger"
              >
                <Download className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="absolute bottom-2 left-2 right-2">
              <p className="text-[10px] font-mono text-white/90 truncate">
                {job.output_width}&times;{job.output_height}
              </p>
              <p className="text-[9px] font-mono text-white/50 uppercase tracking-wider">
                {job.model_name} · {job.scale_factor}&times;
              </p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
