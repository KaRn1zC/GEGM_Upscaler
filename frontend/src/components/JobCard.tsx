import { m, AnimatePresence } from "motion/react";
import {
  CheckCircle2,
  Clock,
  Download,
  Loader2,
  XCircle,
  Zap,
  Ban,
  Sparkles,
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

interface StatusConfig {
  icon: typeof Clock;
  color: string;
  barColor: string;
  glow: boolean;
}

const STATUS_CONFIG: Record<string, StatusConfig> = {
  pending: {
    icon: Clock,
    color: "text-muted-foreground",
    barColor: "bg-muted-foreground",
    glow: false,
  },
  queued: {
    icon: Clock,
    color: "text-warning",
    barColor: "bg-warning",
    glow: false,
  },
  processing: {
    icon: Loader2,
    color: "text-primary",
    barColor: "bg-primary",
    glow: true,
  },
  completed: {
    icon: CheckCircle2,
    color: "text-success",
    barColor: "bg-success",
    glow: false,
  },
  failed: {
    icon: XCircle,
    color: "text-destructive",
    barColor: "bg-destructive",
    glow: false,
  },
  cancelled: {
    icon: Ban,
    color: "text-muted-foreground",
    barColor: "bg-muted-foreground",
    glow: false,
  },
};

export function JobCard({ job, onDownload, onCancel, onCompare }: JobCardProps) {
  const config = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.pending;
  const Icon = config.icon;
  const isActive = job.status === "processing" || job.status === "queued";
  const isProcessing = job.status === "processing";
  const isComplete = job.status === "completed";
  const isFailed = job.status === "failed";
  const pct = Math.round(job.progress * 100);

  return (
    <m.div
      layout
      whileHover={{ y: -2, scale: 1.003 }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className={cn(
        "group relative rounded-xl border bg-card p-5 overflow-hidden transition-colors duration-500",
        isProcessing
          ? "border-primary/40 glow-pulse"
          : isComplete
            ? "border-success/25 hover:border-success/40"
            : isFailed
              ? "border-destructive/30"
              : "border-border hover:border-border/80",
      )}
    >
      {/* Bordure intérieure bleu électrique très subtile sur hover */}
      <div
        className={cn(
          "absolute inset-0 rounded-xl ring-1 ring-inset pointer-events-none transition-all duration-500",
          isProcessing ? "ring-primary/20" : "ring-transparent group-hover:ring-primary/10",
        )}
      />

      {/* En-tête */}
      <div className="relative flex items-start justify-between mb-3.5 gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <m.div
            animate={isProcessing ? { rotate: 360 } : { rotate: 0 }}
            transition={
              isProcessing
                ? { repeat: Infinity, duration: 2, ease: "linear" }
                : { duration: 0.3 }
            }
            className={cn("shrink-0", config.color)}
          >
            <Icon className="w-4 h-4" strokeWidth={1.8} />
          </m.div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground truncate">
              {JOB_STATUS_LABELS[job.status] ?? job.status}
            </p>
            <p
              data-tabular
              className="mt-0.5 text-[10px] font-mono uppercase tracking-[0.1em] text-muted-foreground"
            >
              {job.input_width}×{job.input_height}{" "}
              <span className="text-primary/70 mx-0.5">→</span> {job.scale_factor}×
              {job.output_width && job.output_height && (
                <span className="text-foreground/60">
                  {" "}
                  = {job.output_width}×{job.output_height}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <span className="flex items-center gap-1 text-[9px] font-mono font-medium uppercase tracking-[0.1em] text-muted-foreground px-2 py-1 rounded-md bg-muted border border-border">
            <Sparkles className="w-2.5 h-2.5" strokeWidth={2} />
            {job.model_name}
          </span>
          {job.gpu_backend && (
            <span className="flex items-center gap-1 text-[9px] font-mono font-medium uppercase tracking-[0.1em] text-muted-foreground px-2 py-1 rounded-md bg-muted border border-border">
              <Zap className="w-2.5 h-2.5" strokeWidth={2} />
              {job.gpu_backend}
            </span>
          )}
        </div>
      </div>

      {/* Barre de progression liquide avec shimmer */}
      {(isActive || isComplete) && (
        <div className="relative mb-3.5">
          <div className="flex items-center justify-between mb-1.5">
            <span
              data-tabular
              className={cn(
                "text-[10px] font-mono font-medium",
                isComplete ? "text-success" : "text-primary",
              )}
            >
              {pct}%
            </span>
          </div>
          <div className="relative h-[3px] rounded-full bg-muted overflow-hidden">
            <m.div
              className={cn("absolute inset-y-0 left-0 rounded-full", config.barColor)}
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ type: "spring", stiffness: 180, damping: 30 }}
            />
            {isProcessing && (
              <div className="absolute inset-0 shimmer rounded-full pointer-events-none" />
            )}
          </div>
        </div>
      )}

      {/* Erreur */}
      <AnimatePresence>
        {job.error_message && (
          <m.p
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="text-[11px] text-destructive/85 bg-destructive/5 border border-destructive/20 rounded-lg px-3 py-2 mb-3 font-mono leading-relaxed"
          >
            {job.error_message}
          </m.p>
        )}
      </AnimatePresence>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {isComplete && onCompare && (
          <m.button
            onClick={() => onCompare(job)}
            whileHover={{ scale: 1.03, y: -1 }}
            whileTap={{ scale: 0.96 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            className="text-[11px] font-medium px-3.5 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/15 border border-primary/30 hover:glow-sm transition-all"
          >
            Comparer
          </m.button>
        )}
        {isComplete && onDownload && (
          <m.button
            onClick={() => onDownload(job)}
            whileHover={{ scale: 1.03, y: -1 }}
            whileTap={{ scale: 0.96 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            className="flex items-center gap-1.5 text-[11px] font-medium px-3.5 py-1.5 rounded-lg bg-card border border-border text-foreground hover:border-primary/40 transition-colors"
          >
            <Download className="w-3 h-3" strokeWidth={2} />
            Télécharger
          </m.button>
        )}
        {isActive && onCancel && (
          <m.button
            onClick={() => onCancel(job)}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.96 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            className="text-[11px] font-medium px-3.5 py-1.5 rounded-lg bg-card border border-border text-muted-foreground hover:text-destructive hover:border-destructive/40 transition-colors"
          >
            Annuler
          </m.button>
        )}
        {!isActive && !isComplete && (
          <span
            data-tabular
            className="text-[10px] font-mono uppercase tracking-[0.1em] text-muted-foreground"
          >
            {new Date(job.created_at).toLocaleDateString("fr-FR", {
              day: "numeric",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        )}
      </div>
    </m.div>
  );
}
