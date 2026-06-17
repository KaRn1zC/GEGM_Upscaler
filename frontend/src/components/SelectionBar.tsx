import { m } from "motion/react";
import { Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface SelectionBarProps {
  /** Nombre d'éléments actuellement cochés. */
  selectedCount: number;
  /** Coche tous les éléments supprimables. */
  onSelectAll: () => void;
  /** Lance la suppression groupée (la confirmation est gérée par l'appelant). */
  onDelete: () => void;
  /** Quitte le mode sélection. */
  onClose: () => void;
}

/**
 * Barre flottante de suppression groupée, partagée par l'historique et la
 * galerie. À placer dans un conteneur `relative` (positionnée en bas-centre).
 */
export function SelectionBar({
  selectedCount,
  onSelectAll,
  onDelete,
  onClose,
}: SelectionBarProps) {
  return (
    <m.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 24 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 px-4 py-2.5 rounded-xl bg-popover/95 backdrop-blur-md border border-border ring-1 ring-foreground/10 glow-sm"
    >
      <span data-tabular className="text-[12px] font-mono text-muted-foreground">
        {selectedCount} sélectionné{selectedCount > 1 ? "s" : ""}
      </span>
      <button
        type="button"
        onClick={onSelectAll}
        className="text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        Tout
      </button>
      <button
        type="button"
        disabled={selectedCount === 0}
        onClick={onDelete}
        className={cn(
          "flex items-center gap-1.5 text-[12px] font-medium px-3.5 py-1.5 rounded-lg border transition-colors",
          selectedCount === 0
            ? "bg-card border-border text-muted-foreground/40 cursor-not-allowed"
            : "bg-destructive/15 text-destructive border-destructive/40 hover:bg-destructive/25",
        )}
      >
        <Trash2 className="w-3.5 h-3.5" strokeWidth={1.8} />
        Supprimer
      </button>
      <button
        type="button"
        onClick={onClose}
        className="text-muted-foreground hover:text-foreground transition-colors"
        aria-label="Quitter la sélection"
      >
        <X className="w-4 h-4" strokeWidth={1.8} />
      </button>
    </m.div>
  );
}
