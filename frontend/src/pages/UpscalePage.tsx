import { useCallback, useEffect, useRef, useState } from "react";
import { m, AnimatePresence } from "motion/react";
import { Sparkles } from "lucide-react";
import { DropZone, type DropZoneHandle } from "@/components/DropZone";
import { JobCard } from "@/components/JobCard";
import { CompareSlider } from "@/components/CompareSlider";
import { useUpload } from "@/hooks/useUpload";
import { useSSE } from "@/hooks/useSSE";
import { useSystemResources } from "@/hooks/useSystemResources";
import { useTauriDragDrop } from "@/hooks/useTauriDragDrop";
import { useJobStore } from "@/stores/useJobStore";
import { cn } from "@/lib/utils";
import { SCALE_FACTORS, SCALE_TO_MODEL, type ScaleFactor } from "@/lib/constants";
import {
  getDownloadUrl,
  getUploadUrl,
  warmupGpu,
  type JobResponse,
} from "@/lib/api";
import { downloadFile } from "@/lib/tauri";

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
    cancelJob,
    removeJob,
  } = useJobStore();

  const [scaleFactor, setScaleFactor] = useState<ScaleFactor>(4);
  // Modèle dérivé du scale_factor — le backend applique le même mapping,
  // c'est lui qui tranche. L'UI affiche juste l'info pour transparence.
  const modelLabel = SCALE_TO_MODEL[scaleFactor].label;
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [compareJob, setCompareJob] = useState<JobResponse | null>(null);
  // Fichier choisi (drop, Parcourir, drag-drop Tauri) en attente de
  // lancement explicite via le bouton "Lancer l'upscale" — évite le run
  // automatique qui piégeait l'utilisateur s'il voulait ajuster les settings.
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [isLaunching, setIsLaunching] = useState(false);
  // Verrou synchrone anti-double-clic. Un `useState` n'est pas suffisant
  // car React bat ches l'update : entre deux clics rapides, l'ancien
  // `isLaunching=false` reste visible dans la closure. Le ref est lu et
  // écrit de manière synchrone et préserve l'invariant "un seul run en vol".
  const launchingRef = useRef(false);
  const dropZoneRef = useRef<DropZoneHandle>(null);

  // On a retiré showSettings/setShowSettings — plus de panneau étendu
  // depuis que le modèle est dérivé automatiquement du scale_factor.

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  // Pré-warm GPU : au mount et à chaque changement de facteur, on réveille un
  // worker pour qu'il compile le modèle (torch.compile, ~280 s) pendant que
  // l'utilisateur prépare son upload — le 1er vrai upscale tombe alors sur un
  // worker déjà chaud. Best-effort, n'affiche rien et n'échoue jamais.
  useEffect(() => {
    void warmupGpu(scaleFactor);
  }, [scaleFactor]);

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

  // Déclenche upload + création de job. Appelé par le bouton "Lancer
  // l'upscale" (et non plus directement par la DropZone). L'utilisateur a
  // donc le temps d'ajuster scale_factor / model entre le choix du fichier
  // et le lancement effectif.
  //
  // Verrouillage double : (1) `launchingRef` synchrone pour bloquer
  // immédiatement tout fire supplémentaire pendant la fenêtre async
  // `refreshResources → upload → submitJob`, (2) `isLaunching` pour griser
  // le bouton côté UI. Sans ces deux garde-fous, un clic qui fired plusieurs
  // fois (react strict mode, HMR, etc.) créait N jobs au lieu d'un seul.
  const launchUpscale = useCallback(async () => {
    if (launchingRef.current || !pendingFile || isUploading) return;
    launchingRef.current = true;
    setIsLaunching(true);
    const file = pendingFile;
    try {
      // Refresh juste avant la soumission pour un verdict au plus près
      // de l'état réel (le polling 15 s peut avoir un snapshot trop vieux).
      const verdict = await refreshResources();
      const preferLocal = verdict ? verdict.can_run_local : false;

      const uploaded = await upload(file);
      const job = await submitJob(uploaded.key, scaleFactor, preferLocal);
      setActiveJobId(job.id);
      // Libère la DropZone pour la prochaine image — la preview disparaît,
      // l'utilisateur peut enchaîner.
      setPendingFile(null);
      dropZoneRef.current?.clear();
    } catch {
      // Erreur gérée par useUpload.
    } finally {
      launchingRef.current = false;
      setIsLaunching(false);
    }
  }, [pendingFile, isUploading, upload, submitJob, scaleFactor, refreshResources]);

  // Drag-drop natif depuis Finder (Tauri) — en mode web le hook est no-op
  // et react-dropzone prend le relais. On passe par l'API impérative de
  // DropZone (`acceptFile`) pour que la preview s'affiche comme avec un
  // drag-drop HTML5 ou un clic sur Parcourir.
  const handleNativeDrop = useCallback((files: File[]) => {
    const first = files[0];
    if (first) dropZoneRef.current?.acceptFile(first);
  }, []);
  useTauriDragDrop(handleNativeDrop);

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
          <DropZone
            ref={dropZoneRef}
            onFileAccepted={setPendingFile}
            onFileCleared={() => setPendingFile(null)}
            disabled={isUploading}
          />

          {/* Bouton de lancement — n'apparaît qu'après sélection d'un
              fichier, laissant le temps d'ajuster scale/model avant de
              dispatcher le job sur RunPod. */}
          <AnimatePresence>
            {pendingFile && !isUploading && (
              <m.button
                key="launch-btn"
                onClick={() => void launchUpscale()}
                disabled={isLaunching}
                initial={{ opacity: 0, y: 12, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.96 }}
                whileHover={!isLaunching ? { scale: 1.02, y: -1 } : undefined}
                whileTap={!isLaunching ? { scale: 0.98 } : undefined}
                transition={{ type: "spring", stiffness: 320, damping: 26 }}
                className="mt-6 w-full flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl bg-primary text-primary-foreground font-medium text-sm tracking-wide glow-md hover:glow-lg transition-shadow disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <Sparkles className="w-4 h-4" strokeWidth={2} />
                {isLaunching ? "Lancement…" : "Lancer l'upscale"}
                <span className="font-mono text-xs opacity-80">
                  · ×{scaleFactor} · {modelLabel}
                </span>
              </m.button>
            )}
          </AnimatePresence>

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

          {/* Sélecteur de facteur — choix unique, le modèle est dérivé. */}
          <div className="mt-6 flex items-center gap-3 flex-wrap">
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
            <p className="text-[10px] font-sans uppercase tracking-[0.22em] text-muted-foreground">
              Modèle : <span className="font-mono text-foreground">{modelLabel}</span>
            </p>
          </div>
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
                    <JobCard job={job} onCancel={(j) => void cancelJob(j.id)} />
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
                    onDownload={() => {
                      const filename = job.output_key
                        ? job.output_key.split("/").pop() ?? "upscaled.jpg"
                        : "upscaled.jpg";
                      void downloadFile(getDownloadUrl(job.id), filename);
                    }}
                    onCompare={() => setCompareJob(job)}
                    onDelete={(j) => void removeJob(j.id)}
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
