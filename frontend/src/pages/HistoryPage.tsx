import { useEffect } from "react";
import { m } from "motion/react";
import { Archive } from "lucide-react";
import { JobCard } from "@/components/JobCard";
import { getDownloadUrl } from "@/lib/api";
import { useJobStore } from "@/stores/useJobStore";

const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;

export function HistoryPage() {
  const { jobs, isLoading, fetchJobs } = useJobStore();

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* Halo subtil en haut */}
      <div className="absolute inset-x-0 top-0 h-80 bg-gradient-to-b from-primary/[0.06] to-transparent pointer-events-none" />

      <div className="relative z-10 p-6 lg:p-12 max-w-4xl mx-auto w-full">
        {/* En-tête */}
        <m.header
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO }}
          className="mb-10"
        >
          <h1 className="font-display font-light text-5xl lg:text-7xl tracking-tight text-foreground leading-[0.95]">
            Historique
          </h1>
          <p className="mt-4 text-[11px] uppercase tracking-[0.3em] text-muted-foreground font-sans">
            Tous les jobs d'upscaling soumis
            {jobs.length > 0 && (
              <>
                <span className="mx-2 text-primary/50">·</span>
                <span data-tabular className="text-primary font-mono">
                  {jobs.length}
                </span>
              </>
            )}
          </p>
        </m.header>

        {isLoading && (
          <m.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center justify-center py-24"
          >
            <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          </m.div>
        )}

        {!isLoading && jobs.length === 0 && (
          <m.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.15, ease: EASE_OUT_EXPO }}
            className="flex flex-col items-center justify-center py-24 text-muted-foreground"
          >
            <div className="w-14 h-14 rounded-2xl bg-card border border-border flex items-center justify-center mb-5">
              <Archive className="w-6 h-6 opacity-50" strokeWidth={1.5} />
            </div>
            <p className="font-display font-light text-xl text-foreground">
              Aucun job pour le moment
            </p>
            <p className="text-[10px] uppercase tracking-[0.22em] mt-2 opacity-60">
              Les upscales apparaîtront ici
            </p>
          </m.div>
        )}

        {!isLoading && jobs.length > 0 && (
          <m.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.1, ease: EASE_OUT_EXPO }}
            className="space-y-3"
          >
            {jobs.map((job, i) => (
              <m.div
                key={job.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  type: "spring",
                  stiffness: 260,
                  damping: 24,
                  delay: Math.min(i * 0.04, 0.5),
                }}
              >
                <JobCard
                  job={job}
                  onDownload={
                    job.status === "completed"
                      ? () => window.open(getDownloadUrl(job.id), "_blank")
                      : undefined
                  }
                />
              </m.div>
            ))}
          </m.div>
        )}
      </div>
    </div>
  );
}
