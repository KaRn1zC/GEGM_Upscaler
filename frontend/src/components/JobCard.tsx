import {
  CheckCircle2,
  Clock,
  Download,
  Loader2,
  XCircle,
  Zap,
  Ban,
} from "lucide-react";
import type { JobResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { JOB_STATUS_LABELS } from "@/lib/constants";

interface JobCardProps {
  job: JobResponse;
  onDownload?: (job: JobResponse) => void;
  onCancel?: (job: JobResponse) => void;
  onCompare?: (job: JobResponse) => void;
}

const STATUS_CONFIG: Record<
  string,
  { icon: typeof Clock; color: string; barColor: string }
> = {
  pending: {
    icon: Clock,
    color: "text-muted-foreground",
    barColor: "bg-muted-foreground",
  },
  queued: {
    icon: Clock,
    color: "text-warning",
    barColor: "bg-warning",
  },
  processing: {
    icon: Loader2,
    color: "text-primary",
    barColor: "bg-primary",
  },
  completed: {
    icon: CheckCircle2,
    color: "text-success",
    barColor: "bg-success",
  },
  failed: {
    icon: XCircle,
    color: "text-destructive",
    barColor: "bg-destructive",
  },
  cancelled: {
    icon: Ban,
    color: "text-muted-foreground",
    barColor: "bg-muted-foreground",
  },
};

export function JobCard({ job, onDownload, onCancel, onCompare }: JobCardProps) {
  const config = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.pending;
  const Icon = config.icon;
  const isActive = job.status === "processing" || job.status === "queued";
  const isComplete = job.status === "completed";
  const pct = Math.round(job.progress * 100);

  return (
    <div
      className={cn(
        "group rounded-xl border bg-card p-4 transition-all duration-200",
        isActive
          ? "border-primary/30 shadow-[0_0_20px_rgba(99,102,241,0.06)]"
          : "border-border hover:border-border/80",
      )}
    >
      {/* En-tête : statut + dimensions */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <Icon
            className={cn(
              "w-4 h-4 shrink-0",
              config.color,
              job.status === "processing" && "animate-spin",
            )}
          />
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground truncate">
              {JOB_STATUS_LABELS[job.status] ?? job.status}
            </p>
            <p className="text-xs text-muted-foreground">
              {job.input_width}&times;{job.input_height} &rarr; {job.scale_factor}&times;
              {job.output_width && job.output_height && (
                <span className="text-foreground/70">
                  {" "}
                  = {job.output_width}&times;{job.output_height}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted">
            {job.model_name}
          </span>
          {job.gpu_backend && (
            <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted flex items-center gap-1">
              <Zap className="w-2.5 h-2.5" />
              {job.gpu_backend}
            </span>
          )}
        </div>
      </div>

      {/* Barre de progression */}
      {(isActive || isComplete) && (
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted-foreground">{pct}%</span>
          </div>
          <div className="h-1 rounded-full bg-muted overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500 ease-out",
                config.barColor,
                isActive && "animate-pulse",
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Erreur */}
      {job.error_message && (
        <p className="text-xs text-destructive/80 bg-destructive/5 rounded-lg px-3 py-2 mb-3">
          {job.error_message}
        </p>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        {isComplete && onCompare && (
          <button
            onClick={() => onCompare(job)}
            className="text-xs px-3 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/15 transition-colors"
          >
            Comparer
          </button>
        )}
        {isComplete && onDownload && (
          <button
            onClick={() => onDownload(job)}
            className="text-xs px-3 py-1.5 rounded-lg bg-muted text-foreground hover:bg-muted/80 transition-colors flex items-center gap-1.5"
          >
            <Download className="w-3 h-3" />
            Télécharger
          </button>
        )}
        {isActive && onCancel && (
          <button
            onClick={() => onCancel(job)}
            className="text-xs px-3 py-1.5 rounded-lg bg-muted text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
          >
            Annuler
          </button>
        )}
        {!isActive && !isComplete && (
          <span className="text-xs text-muted-foreground">
            {new Date(job.created_at).toLocaleDateString("fr-FR", {
              day: "numeric",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        )}
      </div>
    </div>
  );
}
