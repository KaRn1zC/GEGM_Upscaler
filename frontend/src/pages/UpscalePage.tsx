import { useCallback, useEffect, useState } from "react";
import { m, AnimatePresence } from "motion/react";
import { Settings2 } from "lucide-react";
import { DropZone } from "@/components/DropZone";
import { JobCard } from "@/components/JobCard";
import { CompareSlider } from "@/components/CompareSlider";
import { useUpload } from "@/hooks/useUpload";
import { useSSE } from "@/hooks/useSSE";
import { useSystemResources } from "@/hooks/useSystemResources";
import { useJobStore } from "@/stores/useJobStore";
import { cn } from "@/lib/utils";
import { MODEL_OPTIONS, SCALE_FACTORS, type ScaleFactor } from "@/lib/constants";
import { getDownloadUrl, getUploadUrl, type JobResponse } from "@/lib/api";

const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;

export function UpscalePage() {
  const { isUploading, progress: uploadProgress, upload } = useUpload();
  const { refresh: refreshResources } = useSystemResources();
  const {
    jobs,
    fetchJobs,
    submitJob,
    updateJobProgress,
    updateJobCompleted,
    updateJobFailed,
    removeJob,
  } = useJobStore();

  const [scaleFactor, setScaleFactor] = useState<ScaleFactor>(4);
  const [modelName, setModelName] = useState<"drct-l" | "hat-l">(
    MODEL_OPTIONS[0].value,
  );
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
        // Refresh juste avant la soumission pour un verdict au plus près
        // de l'état réel (le polling 15 s peut avoir un snapshot trop vieux).
        const verdict = await refreshResources();
        const preferLocal = verdict ? verdict.can_run_local : false;

        const uploaded = await upload(file);
        const job = await submitJob(
          uploaded.key,
          scaleFactor,
          modelName,
          preferLocal,
        );
        setActiveJobId(job.id);
      } catch {
        // Erreur gérée par useUpload.
      }
    },
    [upload, submitJob, scaleFactor, modelName, refreshResources],
  );

  const activeJobs = jobs.filter(
    (j) =>
      j.status === "processing" ||
      j.status === "queued" ||
      j.status === "pending",
  );
  const recentJobs = jobs
    .filter(
      (j) =>
        j.status === "completed" ||
        j.status === "failed" ||
        j.status === "cancelled",
    )
    .slice(0, 5);

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* Background mesh animé — halo signature GEGM */}
      <div className="absolute inset-0 gradient-mesh opacity-50 pointer-events-none" />
      <div className="absolute inset-x-0 top-0 h-96 bg-gradient-to-b from-primary/[0.08] to-transparent pointer-events-none" />

      {/* Contenu principal */}
      <div className="relative z-10 p-6 lg:p-12 max-w-4xl mx-auto w-full">
        {/* En-tête — contraste typo extrême Fraunces × Space Grotesk */}
        <m.header
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO }}
          className="mb-12"
        >
          <h1 className="font-display font-light text-5xl lg:text-7xl tracking-tight text-foreground leading-[0.95]">
            Upscaler
          </h1>
          <p className="mt-4 text-[11px] uppercase tracking-[0.3em] text-muted-foreground font-sans">
            Super-résolution IA — Glisser une image pour commencer
          </p>
        </m.header>

        {/* Comparaison avant/après */}
        <AnimatePresence mode="wait">
          {compareJob && (
            <m.div
              key="compare"
              initial={{ opacity: 0, scale: 0.96, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: -20 }}
              transition={{ type: "spring", stiffness: 260, damping: 26 }}
              className="mb-10"
            >
              <CompareSlider
                beforeSrc={getUploadUrl(compareJob.input_key)}
                afterSrc={getDownloadUrl(compareJob.id)}
                onClose={() => setCompareJob(null)}
              />
            </m.div>
          )}
        </AnimatePresence>

        {/* Zone de drop + paramètres */}
        <m.section
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.1, ease: EASE_OUT_EXPO }}
          className="mb-12"
        >
          <DropZone onFileAccepted={handleFile} disabled={isUploading} />

          {/* Barre d'upload avec shimmer */}
          <AnimatePresence>
            {isUploading && (
              <m.div
                key="upload-bar"
                initial={{ opacity: 0, height: 0, marginTop: 0 }}
                animate={{ opacity: 1, height: "auto", marginTop: 16 }}
                exit={{ opacity: 0, height: 0, marginTop: 0 }}
                transition={{ duration: 0.4, ease: EASE_OUT_EXPO }}
                className="overflow-hidden"
              >
                <div className="relative h-[3px] rounded-full bg-muted overflow-hidden">
                  <m.div
                    className="absolute inset-y-0 left-0 rounded-full bg-primary"
                    initial={{ width: 0 }}
                    animate={{ width: `${uploadProgress}%` }}
                    transition={{ type: "spring", stiffness: 200, damping: 30 }}
                  />
                  <div className="absolute inset-0 shimmer rounded-full" />
                </div>
                <p
                  data-tabular
                  className="mt-2 text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono"
                >
                  Upload {uploadProgress}%
                </p>
              </m.div>
            )}
          </AnimatePresence>

          {/* Paramètres */}
          <div className="mt-6 flex items-center gap-3 flex-wrap">
            <m.button
              onClick={() => setShowSettings((s) => !s)}
              whileHover={{ scale: 1.02, y: -1 }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: "spring", stiffness: 400, damping: 25 }}
              className={cn(
                "flex items-center gap-2 text-xs px-4 py-2 rounded-lg font-medium transition-colors border",
                showSettings
                  ? "bg-primary/10 text-primary border-primary/40"
                  : "bg-card text-muted-foreground hover:text-foreground border-border",
              )}
            >
              <Settings2 className="w-3.5 h-3.5" />
              Paramètres
            </m.button>

            {/* Sélecteur de facteur avec indicateur glissant */}
            <div className="relative flex items-center gap-1 bg-card border border-border rounded-lg p-1">
              {SCALE_FACTORS.map((f) => (
                <m.button
                  key={f}
                  onClick={() => setScaleFactor(f)}
                  whileTap={{ scale: 0.93 }}
                  className="relative z-10 text-xs px-4 py-1.5 rounded-md font-semibold font-mono"
                >
                  {scaleFactor === f && (
                    <m.div
                      layoutId="scale-indicator"
                      className="absolute inset-0 bg-primary rounded-md glow-sm"
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <span
                    data-tabular
                    className={cn(
                      "relative",
                      scaleFactor === f
                        ? "text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground transition-colors",
                    )}
                  >
                    {f}×
                  </span>
                </m.button>
              ))}
            </div>
          </div>

          {/* Panneau paramètres étendu */}
          <AnimatePresence initial={false}>
            {showSettings && (
              <m.div
                key="settings-panel"
                initial={{ opacity: 0, height: 0, marginTop: 0 }}
                animate={{ opacity: 1, height: "auto", marginTop: 12 }}
                exit={{ opacity: 0, height: 0, marginTop: 0 }}
                transition={{ type: "spring", stiffness: 260, damping: 28 }}
                className="overflow-hidden"
              >
                <div className="p-5 rounded-xl border border-border bg-card">
                  <label className="block text-[10px] font-sans uppercase tracking-[0.22em] text-muted-foreground mb-3">
                    Modèle de super-résolution
                  </label>
                  <div className="flex gap-2">
                    {MODEL_OPTIONS.map((option) => (
                      <m.button
                        key={option.value}
                        onClick={() => setModelName(option.value)}
                        whileHover={{ y: -1 }}
                        whileTap={{ scale: 0.96 }}
                        transition={{ type: "spring", stiffness: 400, damping: 25 }}
                        className={cn(
                          "text-xs px-4 py-2.5 rounded-lg border font-medium transition-colors",
                          modelName === option.value
                            ? "border-primary/60 bg-primary/10 text-foreground glow-sm"
                            : "border-border text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {option.label}
                      </m.button>
                    ))}
                  </div>
                </div>
              </m.div>
            )}
          </AnimatePresence>
        </m.section>

        {/* Jobs actifs */}
        <AnimatePresence>
          {activeJobs.length > 0 && (
            <m.section
              key="active-section"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.6, delay: 0.15, ease: EASE_OUT_EXPO }}
              className="mb-10"
            >
              <h2 className="flex items-center gap-2 text-[10px] font-sans uppercase tracking-[0.28em] text-muted-foreground mb-4">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-primary opacity-60 animate-ping" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
                </span>
                En cours
              </h2>
              <div className="space-y-3">
                {activeJobs.map((job, i) => (
                  <m.div
                    key={job.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{
                      type: "spring",
                      stiffness: 260,
                      damping: 24,
                      delay: i * 0.06,
                    }}
                  >
                    <JobCard job={job} onCancel={(j) => void removeJob(j.id)} />
                  </m.div>
                ))}
              </div>
            </m.section>
          )}
        </AnimatePresence>

        {/* Jobs récents */}
        {recentJobs.length > 0 && (
          <m.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.25, ease: EASE_OUT_EXPO }}
          >
            <h2 className="text-[10px] font-sans uppercase tracking-[0.28em] text-muted-foreground mb-4">
              Récents
            </h2>
            <div className="space-y-3">
              {recentJobs.map((job, i) => (
                <m.div
                  key={job.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{
                    type: "spring",
                    stiffness: 260,
                    damping: 24,
                    delay: i * 0.05,
                  }}
                >
                  <JobCard
                    job={job}
                    onDownload={() =>
                      window.open(getDownloadUrl(job.id), "_blank")
                    }
                    onCompare={() => setCompareJob(job)}
                  />
                </m.div>
              ))}
            </div>
          </m.section>
        )}
      </div>
    </div>
  );
}
