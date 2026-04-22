import { m, AnimatePresence } from "motion/react";
import { Download, Sparkles, X } from "lucide-react";
import { useUpdater } from "@/hooks/useUpdater";
import { useUpdaterStore } from "@/stores/useUpdaterStore";

/**
 * Bannière discrète en bas à droite qui notifie d'une mise à jour dispo.
 *
 * Apparaît automatiquement si le check au démarrage trouve une MAJ (phase
 * "available") ou pendant l'installation (phase "downloading"/"installing").
 * No-op hors contexte Tauri (le hook lui-même court-circuite).
 */
export function UpdateBanner() {
  // `useUpdater` fait le check initial au mount ; les autres consommateurs
  // (ex. SettingsPage) lisent le store directement pour éviter de redéclencher.
  useUpdater();
  const { phase, update, progress, error, installAndRestart, dismiss } = useUpdaterStore();

  const percent =
    progress.total > 0 ? Math.round((progress.downloaded / progress.total) * 100) : 0;

  return (
    <AnimatePresence>
      {(phase === "available" ||
        phase === "downloading" ||
        phase === "installing" ||
        phase === "error") && (
        <m.div
          key="update-banner"
          initial={{ opacity: 0, y: 20, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.96 }}
          transition={{ type: "spring", stiffness: 320, damping: 28 }}
          className="fixed bottom-5 right-5 z-50 max-w-sm rounded-xl border border-primary/40 bg-card/95 backdrop-blur-md shadow-xl glow-md overflow-hidden"
        >
          {phase === "available" && update && (
            <div className="p-4">
              <div className="flex items-start gap-3">
                <div className="shrink-0 w-8 h-8 rounded-lg bg-primary/15 text-primary flex items-center justify-center">
                  <Sparkles className="w-4 h-4" strokeWidth={2} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground">
                    Mise à jour disponible
                  </p>
                  <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">
                    v{update.currentVersion} → v{update.version}
                  </p>
                  {update.body && (
                    <p className="mt-2 text-xs text-muted-foreground line-clamp-3">
                      {update.body}
                    </p>
                  )}
                </div>
                <button
                  onClick={dismiss}
                  className="shrink-0 p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="Ignorer la notification"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="mt-4 flex items-center gap-2">
                <m.button
                  onClick={() => void installAndRestart()}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium glow-sm hover:glow-md transition-shadow"
                >
                  <Download className="w-3.5 h-3.5" strokeWidth={2} />
                  Installer et relancer
                </m.button>
                <button
                  onClick={dismiss}
                  className="text-xs text-muted-foreground hover:text-foreground px-3 py-2 transition-colors"
                >
                  Plus tard
                </button>
              </div>
            </div>
          )}

          {(phase === "downloading" || phase === "installing") && (
            <div className="p-4 space-y-3">
              <p className="text-sm font-medium text-foreground">
                {phase === "downloading"
                  ? "Téléchargement de la mise à jour…"
                  : "Installation…"}
              </p>
              <div className="relative h-1 rounded-full bg-muted overflow-hidden">
                <m.div
                  className="absolute inset-y-0 left-0 bg-primary rounded-full"
                  animate={{ width: phase === "installing" ? "100%" : `${percent}%` }}
                  transition={{ type: "spring", stiffness: 200, damping: 30 }}
                />
                <div className="absolute inset-0 shimmer" />
              </div>
              {phase === "downloading" && progress.total > 0 && (
                <p
                  data-tabular
                  className="text-[10px] font-mono text-muted-foreground uppercase tracking-[0.18em]"
                >
                  {Math.round(progress.downloaded / 1024 / 1024)} /{" "}
                  {Math.round(progress.total / 1024 / 1024)} MB · {percent}%
                </p>
              )}
            </div>
          )}

          {phase === "error" && (
            <div className="p-4">
              <p className="text-sm font-medium text-destructive mb-1">
                Échec de la mise à jour
              </p>
              <p className="text-xs text-muted-foreground break-words">
                {error ?? "Erreur inconnue"}
              </p>
              <button
                onClick={dismiss}
                className="mt-3 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                Fermer
              </button>
            </div>
          )}
        </m.div>
      )}
    </AnimatePresence>
  );
}
