/**
 * Pastille indicateur du mode d'exécution courant (local Core ML vs
 * cloud RunPod) basé sur les ressources système détectées.
 *
 * Affiche en permanence le verdict de `canRunLocalStrict()` + permet de
 * consulter le détail des critères dans un modal au clic.
 *
 * En contexte web (sans Tauri), le hook retourne `null` → badge
 * affichant "Cloud" sans pouvoir expliquer (c'est l'environnement
 * browser qui impose cloud).
 */

import { AnimatePresence, m } from "motion/react";
import { Cloud, Info, Zap } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSystemResources } from "@/hooks/useSystemResources";
import { formatResourcesSummary } from "@/lib/capability";
import { cn } from "@/lib/utils";

export function CapabilityBadge() {
  const { decision, refresh } = useSystemResources();
  const [showDetails, setShowDetails] = useState(false);

  // Hors Tauri ou ressources non lues → affichage "cloud" neutre.
  const isLocal = decision?.can_run_local ?? false;
  const snapshot = decision?.snapshot ?? null;
  const blockers = decision?.blockers ?? [];

  const iconCommon = "w-3.5 h-3.5";
  const summary = snapshot ? formatResourcesSummary(snapshot) : null;

  return (
    <>
      <m.button
        type="button"
        onClick={() => setShowDetails(true)}
        whileHover={{ scale: 1.02, y: -1 }}
        whileTap={{ scale: 0.97 }}
        transition={{ type: "spring", stiffness: 400, damping: 25 }}
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 rounded-full border text-[11px]",
          "font-sans uppercase tracking-[0.18em] transition-colors",
          isLocal
            ? "border-primary/40 bg-primary/10 text-primary hover:border-primary/60"
            : "border-border bg-card text-muted-foreground hover:text-foreground hover:border-foreground/30",
        )}
        aria-label={
          isLocal
            ? "Mode local actif — cliquer pour les détails"
            : "Mode cloud — cliquer pour les détails"
        }
      >
        {isLocal ? (
          <Zap className={cn(iconCommon, "fill-primary/30")} />
        ) : (
          <Cloud className={iconCommon} />
        )}
        <span className="font-medium">{isLocal ? "Local" : "Cloud"}</span>
        {summary && (
          <span className="hidden md:inline text-[10px] tracking-normal normal-case opacity-75">
            · {summary}
          </span>
        )}
      </m.button>

      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {isLocal ? (
                <Zap className="w-4 h-4 text-primary" />
              ) : (
                <Cloud className="w-4 h-4 text-muted-foreground" />
              )}
              {isLocal ? "Mode local actif" : "Mode cloud"}
            </DialogTitle>
            <DialogDescription asChild>
              <div className="text-xs text-muted-foreground">
                {isLocal
                  ? "Ton Mac a les ressources suffisantes pour traiter les images ≤ 5 MP en local via Core ML. Les images plus grandes restent traitées sur RunPod Serverless."
                  : "Les images sont traitées sur RunPod Serverless. Le mode local n'est pas disponible pour la raison ci-dessous."}
              </div>
            </DialogDescription>
          </DialogHeader>

          {snapshot && (
            <div className="space-y-4 mt-4">
              {/* Snapshot hardware */}
              <section>
                <h3 className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-2">
                  Machine
                </h3>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs font-mono">
                  <dt className="text-muted-foreground">Chip</dt>
                  <dd>{snapshot.chip}</dd>

                  <dt className="text-muted-foreground">RAM totale</dt>
                  <dd>{snapshot.total_ram_gb.toFixed(0)} Go</dd>

                  {snapshot.macos_version && (
                    <>
                      <dt className="text-muted-foreground">macOS</dt>
                      <dd>{snapshot.macos_version}</dd>
                    </>
                  )}
                </dl>
              </section>

              {/* Snapshot runtime */}
              <section>
                <h3 className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-2">
                  Ressources à l'instant
                </h3>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs font-mono">
                  <dt className="text-muted-foreground">RAM dispo</dt>
                  <dd>{snapshot.available_ram_gb.toFixed(1)} Go</dd>

                  <dt className="text-muted-foreground">Swap</dt>
                  <dd>{snapshot.swap_used_gb.toFixed(1)} Go</dd>

                  <dt className="text-muted-foreground">CPU load</dt>
                  <dd>{(snapshot.cpu_load_1min * 100).toFixed(0)} %</dd>

                  <dt className="text-muted-foreground">Memory pressure</dt>
                  <dd className="capitalize">{snapshot.memory_pressure}</dd>

                  {snapshot.is_on_battery &&
                    snapshot.battery_percent !== null && (
                      <>
                        <dt className="text-muted-foreground">Batterie</dt>
                        <dd>{snapshot.battery_percent} % (débranché)</dd>
                      </>
                    )}
                </dl>
              </section>

              {/* Processus lourds */}
              {snapshot.heavy_processes.length > 0 && (
                <section>
                  <h3 className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-2">
                    Apps lourdes ({snapshot.heavy_processes.length})
                  </h3>
                  <ul className="space-y-1 text-xs font-mono">
                    {snapshot.heavy_processes.slice(0, 5).map((p) => (
                      <li
                        key={p.name}
                        className="flex justify-between text-muted-foreground"
                      >
                        <span className="truncate mr-4">{p.name}</span>
                        <span>{p.ram_gb.toFixed(1)} Go</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Raisons de blocage */}
              <AnimatePresence>
                {!isLocal && blockers.length > 0 && (
                  <m.section
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="rounded-lg border border-destructive/30 bg-destructive/5 p-3"
                  >
                    <h3 className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-destructive mb-2">
                      <Info className="w-3 h-3" />
                      Raisons du fallback cloud
                    </h3>
                    <ul className="space-y-1 text-xs font-mono text-destructive/90">
                      {blockers.map((reason) => (
                        <li key={reason} className="flex gap-2">
                          <span className="text-destructive/50">·</span>
                          <span>{reason}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-2 text-[10px] text-muted-foreground italic">
                      Fermer des applications lourdes peut débloquer le mode
                      local.
                    </p>
                  </m.section>
                )}
              </AnimatePresence>
            </div>
          )}

          <div className="mt-4 flex justify-between items-center">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                void refresh();
              }}
            >
              Rafraîchir
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowDetails(false)}
            >
              Fermer
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
