import { useEffect, useState } from "react";
import { ImageIcon } from "lucide-react";
import { Gallery } from "@/components/Gallery";
import { ZoomViewer } from "@/components/ZoomViewer";
import { useJobStore } from "@/stores/useJobStore";
import type { JobResponse } from "@/lib/api";

export function GalleryPage() {
  const { jobs, isLoading, fetchJobs } = useJobStore();
  const [zoomJob, setZoomJob] = useState<JobResponse | null>(null);

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  const completedJobs = jobs.filter((j) => j.status === "completed");

  return (
    <div className="flex-1 p-6 lg:p-10 max-w-6xl mx-auto w-full">
      {/* En-tête */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-foreground tracking-tight">
          Galerie
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Tous les résultats d'upscaling terminés
        </p>
      </div>

      {/* Viewer plein écran */}
      {zoomJob && (
        <div className="mb-8">
          <ZoomViewer
            imageUrl={`/api/jobs/${zoomJob.id}/download`}
            title={`${zoomJob.output_width}×${zoomJob.output_height} · ${zoomJob.model_name}`}
            onClose={() => setZoomJob(null)}
          />
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        </div>
      )}

      {!isLoading && completedJobs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <ImageIcon className="w-10 h-10 mb-4 opacity-40" />
          <p className="text-sm">Aucun résultat disponible</p>
          <p className="text-xs mt-1 opacity-60">
            Les images upscalées apparaîtront ici
          </p>
        </div>
      )}

      {!isLoading && completedJobs.length > 0 && (
        <Gallery jobs={completedJobs} onZoom={setZoomJob} />
      )}
    </div>
  );
}
