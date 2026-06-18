import { useEffect, useState } from "react";
import { m, AnimatePresence } from "motion/react";
import { ImageIcon } from "lucide-react";
import { Gallery } from "@/components/Gallery";
import { ZoomViewer } from "@/components/ZoomViewer";
import { CompareSlider } from "@/components/CompareSlider";
import { SelectionBar } from "@/components/SelectionBar";
import { useConfirm } from "@/hooks/useConfirm";
import { useJobStore } from "@/stores/useJobStore";
import { getDownloadUrl, getUploadUrl, type JobResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;

export function GalleryPage() {
  const { jobs, isLoading, fetchJobs, removeJob, removeJobs } = useJobStore();
  const confirm = useConfirm();
  const [zoomJob, setZoomJob] = useState<JobResponse | null>(null);
  const [compareJob, setCompareJob] = useState<JobResponse | null>(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Le zoom et la comparaison sont deux vues mutuellement exclusives : ouvrir
  // l'une ferme l'autre.
  const openZoom = (job: JobResponse) => {
    setCompareJob(null);
    setZoomJob(job);
  };
  const openCompare = (job: JobResponse) => {
    setZoomJob(null);
    setCompareJob(job);
  };

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  const completedJobs = jobs.filter((j) => j.status === "completed");

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

  const handleBulkDelete = async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    const ok = await confirm({
      title: `Supprimer ${ids.length} résultat(s) ?`,
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
      {/* Halo subtil en haut */}
      <div className="absolute inset-x-0 top-0 h-80 bg-gradient-to-b from-primary/[0.06] to-transparent pointer-events-none" />

      <div className="relative z-10 p-6 lg:p-12 max-w-6xl mx-auto w-full">
        {/* En-tête */}
        <m.header
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO }}
          className="mb-10 flex items-end justify-between gap-4"
        >
          <div>
            <h1 className="font-display font-light text-5xl lg:text-7xl tracking-tight text-foreground leading-[0.95]">
              Galerie
            </h1>
            <p className="mt-4 text-[11px] uppercase tracking-[0.3em] text-muted-foreground font-sans">
              Tous les résultats d'upscaling terminés
              {completedJobs.length > 0 && (
                <>
                  <span className="mx-2 text-primary/50">·</span>
                  <span data-tabular className="text-primary font-mono">
                    {completedJobs.length}
                  </span>
                </>
              )}
            </p>
          </div>

          {completedJobs.length > 0 && !zoomJob && !compareJob && (
            <button
              type="button"
              onClick={() => (selectMode ? exitSelection() : setSelectMode(true))}
              className={cn(
                "shrink-0 text-[11px] font-medium px-3.5 py-1.5 rounded-lg border bg-card transition-colors",
                selectMode
                  ? "border-border text-muted-foreground hover:text-foreground"
                  : "border-border text-muted-foreground hover:text-primary hover:border-primary/40",
              )}
            >
              {selectMode ? "Terminer" : "Sélectionner"}
            </button>
          )}
        </m.header>

        {/* Viewer plein écran avec shared layout */}
        <AnimatePresence mode="wait">
          {zoomJob && (
            <m.div
              key={`viewer-${zoomJob.id}`}
              layoutId={`job-card-${zoomJob.id}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4, ease: EASE_OUT_EXPO }}
              className="mb-10"
            >
              <ZoomViewer
                imageUrl={getDownloadUrl(zoomJob.id)}
                title={`${zoomJob.output_width}×${zoomJob.output_height} · ${zoomJob.model_name}`}
                onClose={() => setZoomJob(null)}
                onDelete={() => {
                  void removeJob(zoomJob.id);
                  setZoomJob(null);
                }}
              />
            </m.div>
          )}
        </AnimatePresence>

        {/* Comparateur avant/après (slider) */}
        <AnimatePresence mode="wait">
          {compareJob && (
            <m.div
              key={`compare-${compareJob.id}`}
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

        {isLoading && (
          <m.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center justify-center py-24"
          >
            <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          </m.div>
        )}

        {!isLoading && completedJobs.length === 0 && (
          <m.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.15, ease: EASE_OUT_EXPO }}
            className="flex flex-col items-center justify-center py-24 text-muted-foreground"
          >
            <div className="w-14 h-14 rounded-2xl bg-card border border-border flex items-center justify-center mb-5">
              <ImageIcon className="w-6 h-6 opacity-50" strokeWidth={1.5} />
            </div>
            <p className="font-display font-light text-xl text-foreground">
              Aucun résultat disponible
            </p>
            <p className="text-[10px] uppercase tracking-[0.22em] mt-2 opacity-60">
              Les images upscalées apparaîtront ici
            </p>
          </m.div>
        )}

        {!isLoading && completedJobs.length > 0 && (
          <Gallery
            jobs={completedJobs}
            onZoom={selectMode ? undefined : openZoom}
            onCompare={selectMode ? undefined : openCompare}
            onDelete={(j) => void removeJob(j.id)}
            selectMode={selectMode}
            selectedIds={selected}
            onToggleSelect={toggle}
          />
        )}
      </div>

      {/* Barre d'action de sélection groupée */}
      <AnimatePresence>
        {selectMode && (
          <SelectionBar
            selectedCount={selected.size}
            onSelectAll={() => setSelected(new Set(completedJobs.map((j) => j.id)))}
            onDelete={() => void handleBulkDelete()}
            onClose={exitSelection}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
