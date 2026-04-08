import { useCallback, useEffect, useState } from "react";
import { Settings2 } from "lucide-react";
import { DropZone } from "@/components/DropZone";
import { JobCard } from "@/components/JobCard";
import { CompareSlider } from "@/components/CompareSlider";
import { useUpload } from "@/hooks/useUpload";
import { useSSE } from "@/hooks/useSSE";
import { useJobStore } from "@/stores/useJobStore";
import { cn } from "@/lib/utils";
import { MODEL_OPTIONS, SCALE_FACTORS, type ScaleFactor } from "@/lib/constants";
import type { JobResponse } from "@/lib/api";

export function UpscalePage() {
  const { isUploading, progress: uploadProgress, upload } = useUpload();
  const { jobs, fetchJobs, submitJob, updateJobProgress, updateJobCompleted, updateJobFailed, removeJob } =
    useJobStore();

  const [scaleFactor, setScaleFactor] = useState<ScaleFactor>(4);
  const [modelName, setModelName] = useState(MODEL_OPTIONS[0].value);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [compareJob, setCompareJob] = useState<JobResponse | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  // SSE pour le job actif.
  useSSE({
    jobId: activeJobId,
    onProgress: useCallback(
      (data) => updateJobProgress(data.job_id, data.progress, data.status),
      [updateJobProgress],
    ),
    onComplete: useCallback(
      (data) => {
        updateJobCompleted(data.job_id, data.output_key ?? "");
        setActiveJobId(null);
      },
      [updateJobCompleted],
    ),
    onError: useCallback(
      (data) => {
        updateJobFailed(data.job_id, data.error_message ?? "Erreur inconnue");
        setActiveJobId(null);
      },
      [updateJobFailed],
    ),
  });

  const handleFile = useCallback(
    async (file: File) => {
      try {
        const uploaded = await upload(file);
        const job = await submitJob(uploaded.key, scaleFactor, modelName);
        setActiveJobId(job.id);
      } catch {
        // Erreur gérée par useUpload.
      }
    },
    [upload, submitJob, scaleFactor, modelName],
  );

  const activeJobs = jobs.filter(
    (j) => j.status === "processing" || j.status === "queued" || j.status === "pending",
  );
  const recentJobs = jobs.filter(
    (j) => j.status === "completed" || j.status === "failed" || j.status === "cancelled",
  ).slice(0, 5);

  return (
    <div className="flex-1 p-6 lg:p-10 max-w-4xl mx-auto w-full">
      {/* En-tête */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-foreground tracking-tight">Upscaler</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Super-résolution IA — glisser une image pour commencer
        </p>
      </div>

      {/* Comparaison avant/après */}
      {compareJob && (
        <div className="mb-8">
          <CompareSlider
            beforeSrc={`/api/uploads/${compareJob.input_key}`}
            afterSrc={`/api/jobs/${compareJob.id}/download`}
            onClose={() => setCompareJob(null)}
          />
        </div>
      )}

      {/* Zone de drop + paramètres */}
      <div className="mb-8">
        <DropZone onFileAccepted={handleFile} disabled={isUploading} />

        {/* Barre d'upload */}
        {isUploading && (
          <div className="mt-3">
            <div className="h-1 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground mt-1">Upload {uploadProgress}%</p>
          </div>
        )}

        {/* Paramètres */}
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={() => setShowSettings((s) => !s)}
            className={cn(
              "flex items-center gap-2 text-xs px-3 py-2 rounded-lg transition-colors",
              showSettings
                ? "bg-primary/10 text-primary"
                : "bg-muted text-muted-foreground hover:text-foreground",
            )}
          >
            <Settings2 className="w-3.5 h-3.5" />
            Paramètres
          </button>

          {/* Sélecteur de facteur toujours visible */}
          <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
            {SCALE_FACTORS.map((f) => (
              <button
                key={f}
                onClick={() => setScaleFactor(f)}
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
        </div>

        {/* Panneau paramètres étendu */}
        {showSettings && (
          <div className="mt-3 p-4 rounded-xl border border-border bg-card">
            <label className="block text-xs text-muted-foreground mb-2">Modèle</label>
            <div className="flex gap-2">
              {MODEL_OPTIONS.map((m) => (
                <button
                  key={m.value}
                  onClick={() => setModelName(m.value)}
                  className={cn(
                    "text-xs px-3 py-2 rounded-lg border transition-all",
                    modelName === m.value
                      ? "border-primary/50 bg-primary/5 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground hover:border-border/80",
                  )}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Jobs actifs */}
      {activeJobs.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
            En cours
          </h2>
          <div className="space-y-3">
            {activeJobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                onCancel={(j) => void removeJob(j.id)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Jobs récents */}
      {recentJobs.length > 0 && (
        <section>
          <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
            Récents
          </h2>
          <div className="space-y-3">
            {recentJobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                onDownload={() =>
                  window.open(`/api/jobs/${job.id}/download`, "_blank")
                }
                onCompare={() => setCompareJob(job)}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
