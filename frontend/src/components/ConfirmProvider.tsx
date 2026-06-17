import { useCallback, useState, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ConfirmContext,
  type ConfirmFn,
  type ConfirmOptions,
} from "@/hooks/useConfirm";
import { cn } from "@/lib/utils";

interface PendingState extends ConfirmOptions {
  resolve: (value: boolean) => void;
}

/**
 * Fournit un dialog de confirmation unique, piloté par `useConfirm()`.
 *
 * Un seul `<Dialog>` est monté pour toute l'app ; chaque appel à `confirm()`
 * renvoie une promesse résolue à `true` (action confirmée) ou `false`
 * (annulation / fermeture).
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingState | null>(null);
  // Conserve les dernières options en state (pas un ref) pour que le titre/
  // texte restent affichés pendant l'animation de fermeture du dialog.
  const [lastOptions, setLastOptions] = useState<ConfirmOptions | null>(null);

  const confirm = useCallback<ConfirmFn>((options) => {
    setLastOptions(options);
    return new Promise<boolean>((resolve) => {
      setPending({ ...options, resolve });
    });
  }, []);

  const settle = useCallback(
    (value: boolean) => {
      setPending((current) => {
        current?.resolve(value);
        return null;
      });
    },
    [],
  );

  const view = pending ?? lastOptions;
  const destructive = view?.destructive ?? true;

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Dialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) settle(false);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {destructive && (
                <AlertTriangle
                  className="w-4 h-4 text-destructive shrink-0"
                  strokeWidth={2}
                />
              )}
              {view?.title}
            </DialogTitle>
            {view?.description && (
              <DialogDescription>{view.description}</DialogDescription>
            )}
          </DialogHeader>
          <DialogFooter>
            <button
              type="button"
              onClick={() => settle(false)}
              className="text-[13px] font-medium px-4 py-2 rounded-lg bg-card border border-border text-muted-foreground hover:text-foreground hover:border-border/80 transition-colors"
            >
              {view?.cancelLabel ?? "Annuler"}
            </button>
            <button
              type="button"
              onClick={() => settle(true)}
              autoFocus
              className={cn(
                "text-[13px] font-medium px-4 py-2 rounded-lg border transition-colors",
                destructive
                  ? "bg-destructive/15 text-destructive border-destructive/40 hover:bg-destructive/25"
                  : "bg-primary/15 text-primary border-primary/40 hover:bg-primary/25",
              )}
            >
              {view?.confirmLabel ?? "Confirmer"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ConfirmContext.Provider>
  );
}
