import { useCallback, useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { BatchPanel } from "@/components/BatchPanel";
import { JobCard } from "@/components/JobCard";
import { useJobStore } from "@/stores/useJobStore";
import type { ScaleFactor } from "@/lib/constants";

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
    <div className="flex-1 p-6 lg:p-10 max-w-5xl mx-auto w-full">
      {/* En-tête */}
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground tracking-tight">
            Traitement batch
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Traiter plusieurs images en parallèle
          </p>
        </div>

        {totalCount > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted text-xs font-mono">
            <Layers className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">
              {completedCount}/{totalCount} terminés
            </span>
          </div>
        )}
      </div>

      {/* Panneau batch */}
      <div className="mb-8">
        <BatchPanel onSubmit={handleSubmit} isSubmitting={isSubmitting} />
      </div>

      {/* Erreurs du dernier batch */}
      {lastBatchErrors.length > 0 && (
        <div className="mb-8 p-4 rounded-xl border border-destructive/30 bg-destructive/5">
          <p className="text-xs font-medium text-destructive mb-2">
            {lastBatchErrors.length} erreur{lastBatchErrors.length > 1 ? "s" : ""} lors de la soumission
          </p>
          <ul className="space-y-1">
            {lastBatchErrors.map((err, i) => (
              <li key={i} className="text-xs text-destructive/80 font-mono">
                · {err}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Jobs actifs */}
      {activeJobs.length > 0 && (
        <section>
          <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
            En cours ({activeJobs.length})
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
    </div>
  );
}
