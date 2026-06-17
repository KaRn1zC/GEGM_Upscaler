import { useCallback } from "react";
import { JobCard } from "@/components/JobCard";
import { useSSE } from "@/hooks/useSSE";
import { useJobStore } from "@/stores/useJobStore";
import type { JobResponse } from "@/lib/api";

interface LiveJobCardProps {
  job: JobResponse;
  onDownload?: (job: JobResponse) => void;
  onCancel?: (job: JobResponse) => void;
  onCompare?: (job: JobResponse) => void;
  onDelete?: (job: JobResponse) => void;
}

const ACTIVE = new Set(["pending", "queued", "processing"]);

/**
 * `JobCard` qui s'abonne lui-même au flux SSE de progression tant que le job
 * est actif. Permet d'avoir une barre vivante sur plusieurs jobs à la fois
 * (batch) — là où `UpscalePage` n'abonne qu'un seul job. L'abonnement se coupe
 * automatiquement dès que le job devient terminal (jobId passé à `null`).
 */
export function LiveJobCard({ job, ...cardProps }: LiveJobCardProps) {
  const updateJobProgress = useJobStore((s) => s.updateJobProgress);
  const updateJobCompleted = useJobStore((s) => s.updateJobCompleted);
  const updateJobFailed = useJobStore((s) => s.updateJobFailed);

  useSSE({
    jobId: ACTIVE.has(job.status) ? job.id : null,
    onProgress: useCallback(
      (data) => updateJobProgress(data.job_id, data.progress, data.status),
      [updateJobProgress],
    ),
    onComplete: useCallback(
      (data) => updateJobCompleted(data.job_id, data.output_key ?? ""),
      [updateJobCompleted],
    ),
    onError: useCallback(
      (data) => updateJobFailed(data.job_id, data.error_message ?? "Erreur inconnue"),
      [updateJobFailed],
    ),
  });

  return <JobCard job={job} {...cardProps} />;
}
