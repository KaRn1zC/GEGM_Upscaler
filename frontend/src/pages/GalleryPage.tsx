import { useEffect, useState } from "react";
import { m, AnimatePresence } from "motion/react";
import { ImageIcon } from "lucide-react";
import { Gallery } from "@/components/Gallery";
import { ZoomViewer } from "@/components/ZoomViewer";
import { useJobStore } from "@/stores/useJobStore";
import type { JobResponse } from "@/lib/api";

const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;

export function GalleryPage() {
  const { jobs, isLoading, fetchJobs } = useJobStore();
  const [zoomJob, setZoomJob] = useState<JobResponse | null>(null);

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  const completedJobs = jobs.filter((j) => j.status === "completed");

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* Halo subtil en haut */}
      <div className="absolute inset-x-0 top-0 h-80 bg-gradient-to-b from-primary/[0.06] to-transparent pointer-events-none" />

      <div className="relative z-10 p-6 lg:p-12 max-w-6xl mx-auto w-full">
        {/* En-tête */}
        <m.header
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO }}
          className="mb-10"
        >
          <h1 className="font-display font-light text-5xl lg:text-7xl tracking-tight text-foreground leading-[0.95]">
            Galerie
          </h1>
          <p className="mt-4 text-[11px] uppercase tracking-[0.3em] text-muted-foreground font-sans">
            Tous les résultats d'upscaling terminés
            {completedJobs.length > 0 && (
              <>
                <span className="mx-2 text-primary/50">·</span>
                <span data-tabular className="text-primary font-mono">
                  {completedJobs.length}
                </span>
              </>
            )}
          </p>
        </m.header>

        {/* Viewer plein écran avec shared layout */}
        <AnimatePresence mode="wait">
          {zoomJob && (
            <m.div
              key={`viewer-${zoomJob.id}`}
              layoutId={`job-card-${zoomJob.id}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4, ease: EASE_OUT_EXPO }}
              className="mb-10"
            >
              <ZoomViewer
                imageUrl={`/api/jobs/${zoomJob.id}/download`}
                title={`${zoomJob.output_width}×${zoomJob.output_height} · ${zoomJob.model_name}`}
                onClose={() => setZoomJob(null)}
              />
            </m.div>
          )}
        </AnimatePresence>

        {isLoading && (
          <m.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center justify-center py-24"
          >
            <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          </m.div>
        )}

        {!isLoading && completedJobs.length === 0 && (
          <m.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.15, ease: EASE_OUT_EXPO }}
            className="flex flex-col items-center justify-center py-24 text-muted-foreground"
          >
            <div className="w-14 h-14 rounded-2xl bg-card border border-border flex items-center justify-center mb-5">
              <ImageIcon className="w-6 h-6 opacity-50" strokeWidth={1.5} />
            </div>
            <p className="font-display font-light text-xl text-foreground">
              Aucun résultat disponible
            </p>
            <p className="text-[10px] uppercase tracking-[0.22em] mt-2 opacity-60">
              Les images upscalées apparaîtront ici
            </p>
          </m.div>
        )}

        {!isLoading && completedJobs.length > 0 && (
          <Gallery jobs={completedJobs} onZoom={setZoomJob} />
        )}
      </div>
    </div>
  );
}
