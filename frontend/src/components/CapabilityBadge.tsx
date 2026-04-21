/**
 * Pastille indicateur du mode d'exécution courant.
 *
 * **v1 (actuelle)** : traitement cloud exclusif via RunPod Serverless. Le
 * mode local Core ML est désactivé car la conversion PyTorch → `.mlpackage`
 * de DRCT-L et HAT-L n'a pas abouti (incompatibilité coremltools avec les
 * `int(tensor)` implicites du window-partitioning Swin). Les critères de
 * capacité sont toujours évalués pour affichage informatif — ils
 * redeviendront décisionnels quand le local sera réactivé (v2).
 */

import { m } from "motion/react";
import { Cloud, Info } from "lucide-react";
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

  // v1 : cloud exclusif. Le snapshot reste affiché en info dans le dialog.
  const snapshot = decision?.snapshot ?? null;

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
          "border-border bg-card text-muted-foreground hover:text-foreground hover:border-foreground/30",
        )}
        aria-label="Mode cloud — cliquer pour les détails"
      >
        <Cloud className={iconCommon} />
        <span className="font-medium">Cloud</span>
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
              <Cloud className="w-4 h-4 text-muted-foreground" />
              Mode cloud (RunPod)
            </DialogTitle>
            <DialogDescription asChild>
              <div className="text-xs text-muted-foreground">
                Tous les traitements passent par RunPod Serverless. Le mode
                local Core ML est prévu pour une prochaine version : la
                conversion PyTorch → <code>.mlpackage</code> de DRCT-L / HAT-L
                s'est heurtée à une incompatibilité coremltools sur les
                opérations <code>int(tensor)</code> du window-partitioning
                Swin. Les capteurs de ressources restent actifs pour
                préparer la réactivation.
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

              {/* Note v1 — local désactivé */}
              <section className="rounded-lg border border-border bg-card p-3">
                <h3 className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-2">
                  <Info className="w-3 h-3" />
                  Mode local (v2)
                </h3>
                <p className="text-xs text-muted-foreground">
                  Le snapshot ci-dessus sera utilisé pour décider
                  local vs cloud dès que la conversion Core ML des modèles
                  sera débloquée.
                </p>
              </section>
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
