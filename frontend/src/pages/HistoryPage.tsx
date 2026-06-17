import { useEffect, useMemo, useState } from "react";
import { m, AnimatePresence } from "motion/react";
import { Archive, CheckSquare, Square } from "lucide-react";
import { JobCard } from "@/components/JobCard";
import { SelectionBar } from "@/components/SelectionBar";
import { useConfirm } from "@/hooks/useConfirm";
import { getDownloadUrl, type JobResponse } from "@/lib/api";
import { downloadFile } from "@/lib/tauri";
import { useJobStore } from "@/stores/useJobStore";
import { cn } from "@/lib/utils";

const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export function HistoryPage() {
  const { jobs, isLoading, fetchJobs, cancelJob, removeJob, removeJobs } =
    useJobStore();
  const confirm = useConfirm();

  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  // Jobs supprimables (terminés) — base de la sélection groupée.
  const deletableIds = useMemo(
    () => jobs.filter((j) => TERMINAL.has(j.status)).map((j) => j.id),
    [jobs],
  );

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const exitSelection = () => {
    setSelectMode(false);
    setSelected(new Set());
  };

  const handleDownload = (job: JobResponse) => {
    const filename = job.output_key
      ? job.output_key.split("/").pop() ?? "upscaled.jpg"
      : "upscaled.jpg";
    void downloadFile(getDownloadUrl(job.id), filename);
  };

  const handleBulkDelete = async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    const ok = await confirm({
      title: `Supprimer ${ids.length} job(s) ?`,
      description:
        "Les images sources et résultats sélectionnés seront définitivement supprimés du stockage. Cette action est irréversible.",
      confirmLabel: "Supprimer",
    });
    if (!ok) return;
    await removeJobs(ids);
    exitSelection();
  };

  return (
    <div className="relative flex-1 overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-80 bg-gradient-to-b from-primary/[0.06] to-transparent pointer-events-none" />

      <div className="relative z-10 p-6 lg:p-12 max-w-4xl mx-auto w-full">
        {/* En-tête */}
        <m.header
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO }}
          className="mb-10 flex items-end justify-between gap-4"
        >
          <div>
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
          </div>

          {deletableIds.length > 0 && (
            <button
              type="button"
              onClick={() => (selectMode ? exitSelection() : setSelectMode(true))}
              className={cn(
                "shrink-0 text-[11px] font-medium px-3.5 py-1.5 rounded-lg border transition-colors",
                selectMode
                  ? "bg-card border-border text-muted-foreground hover:text-foreground"
                  : "bg-card border-border text-muted-foreground hover:text-primary hover:border-primary/40",
              )}
            >
              {selectMode ? "Terminer" : "Sélectionner"}
            </button>
          )}
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
            {jobs.map((job, i) => {
              const selectable = selectMode && TERMINAL.has(job.status);
              const isChecked = selected.has(job.id);
              return (
                <m.div
                  key={job.id}
                  layout
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{
                    type: "spring",
                    stiffness: 260,
                    damping: 24,
                    delay: Math.min(i * 0.04, 0.5),
                  }}
                  className="flex items-stretch gap-3"
                >
                  {selectMode && (
                    <button
                      type="button"
                      disabled={!selectable}
                      onClick={() => selectable && toggle(job.id)}
                      className={cn(
                        "shrink-0 self-center transition-colors",
                        selectable
                          ? isChecked
                            ? "text-primary"
                            : "text-muted-foreground hover:text-foreground"
                          : "text-muted-foreground/30 cursor-not-allowed",
                      )}
                      aria-label={isChecked ? "Désélectionner" : "Sélectionner"}
                    >
                      {isChecked ? (
                        <CheckSquare className="w-5 h-5" strokeWidth={1.8} />
                      ) : (
                        <Square className="w-5 h-5" strokeWidth={1.8} />
                      )}
                    </button>
                  )}
                  <div className="flex-1 min-w-0">
                    <JobCard
                      job={job}
                      onDownload={
                        job.status === "completed"
                          ? () => handleDownload(job)
                          : undefined
                      }
                      onCancel={(j) => void cancelJob(j.id)}
                      onDelete={(j) => void removeJob(j.id)}
                    />
                  </div>
                </m.div>
              );
            })}
          </m.div>
        )}
      </div>

      {/* Barre d'action de sélection groupée */}
      <AnimatePresence>
        {selectMode && (
          <SelectionBar
            selectedCount={selected.size}
            onSelectAll={() => setSelected(new Set(deletableIds))}
            onDelete={() => void handleBulkDelete()}
            onClose={exitSelection}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
