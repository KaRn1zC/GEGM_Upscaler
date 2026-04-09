import { useCallback, useEffect, useState } from "react";
import { m, AnimatePresence } from "motion/react";
import { Layers } from "lucide-react";
import { BatchPanel } from "@/components/BatchPanel";
import { JobCard } from "@/components/JobCard";
import { useJobStore } from "@/stores/useJobStore";
import type { ScaleFactor } from "@/lib/constants";

const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;

export function BatchPage() {
  const { jobs, fetchJobs, submitBatch, removeJob } = useJobStore();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastBatchErrors, setLastBatchErrors] = useState<string[]>([]);

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  const handleSubmit = useCallback(
    async (files: File[], scaleFactor: ScaleFactor) => {
      setIsSubmitting(true);
      setLastBatchErrors([]);
      try {
        const results = await submitBatch(files, scaleFactor);
        const errors = results
          .filter((r) => r.error !== null)
          .map((r) => `${r.file.name} : ${r.error}`);
        setLastBatchErrors(errors);
      } finally {
        setIsSubmitting(false);
      }
    },
    [submitBatch],
  );

  const activeJobs = jobs.filter(
    (j) =>
      j.status === "processing" ||
      j.status === "queued" ||
      j.status === "pending",
  );

  const totalCount = jobs.length;
  const completedCount = jobs.filter((j) => j.status === "completed").length;

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* Halo subtil en haut */}
      <div className="absolute inset-x-0 top-0 h-80 bg-gradient-to-b from-primary/[0.06] to-transparent pointer-events-none" />

      <div className="relative z-10 p-6 lg:p-12 max-w-5xl mx-auto w-full">
        {/* En-tête */}
        <m.header
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO }}
          className="mb-10 flex items-start justify-between gap-6 flex-wrap"
        >
          <div>
            <h1 className="font-display font-light text-5xl lg:text-7xl tracking-tight text-foreground leading-[0.95]">
              Batch
            </h1>
            <p className="mt-4 text-[11px] uppercase tracking-[0.3em] text-muted-foreground font-sans">
              Traiter plusieurs images en parallèle
            </p>
          </div>

          {totalCount > 0 && (
            <m.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.3, duration: 0.5, ease: EASE_OUT_EXPO }}
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-card border border-border mt-2"
            >
              <Layers className="w-3.5 h-3.5 text-primary" strokeWidth={2} />
              <span
                data-tabular
                className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground"
              >
                <span className="text-primary font-semibold">
                  {completedCount}
                </span>
                <span className="mx-1 opacity-40">/</span>
                <span className="text-foreground">{totalCount}</span>
                <span className="ml-1.5">terminés</span>
              </span>
            </m.div>
          )}
        </m.header>

        {/* Panneau batch */}
        <m.section
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.1, ease: EASE_OUT_EXPO }}
          className="mb-12"
        >
          <BatchPanel onSubmit={handleSubmit} isSubmitting={isSubmitting} />
        </m.section>

        {/* Erreurs du dernier batch */}
        <AnimatePresence>
          {lastBatchErrors.length > 0 && (
            <m.div
              initial={{ opacity: 0, y: -8, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, y: -8, height: 0 }}
              transition={{ type: "spring", stiffness: 260, damping: 26 }}
              className="mb-10 overflow-hidden"
            >
              <div className="p-4 rounded-xl border border-destructive/30 bg-destructive/5">
                <p className="text-[10px] font-sans uppercase tracking-[0.22em] font-medium text-destructive mb-2">
                  {lastBatchErrors.length} erreur
                  {lastBatchErrors.length > 1 ? "s" : ""} lors de la soumission
                </p>
                <ul className="space-y-1">
                  {lastBatchErrors.map((err, i) => (
                    <li
                      key={i}
                      className="text-[11px] text-destructive/80 font-mono"
                    >
                      · {err}
                    </li>
                  ))}
                </ul>
              </div>
            </m.div>
          )}
        </AnimatePresence>

        {/* Jobs actifs */}
        <AnimatePresence>
          {activeJobs.length > 0 && (
            <m.section
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease: EASE_OUT_EXPO }}
            >
              <h2 className="flex items-center gap-2 text-[10px] font-sans uppercase tracking-[0.28em] text-muted-foreground mb-4">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-primary opacity-60 animate-ping" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
                </span>
                En cours ({activeJobs.length})
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
                      delay: i * 0.05,
                    }}
                  >
                    <JobCard
                      job={job}
                      onCancel={(j) => void removeJob(j.id)}
                    />
                  </m.div>
                ))}
              </div>
            </m.section>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
