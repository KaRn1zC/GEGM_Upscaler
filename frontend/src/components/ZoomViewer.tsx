import { m } from "motion/react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import { X, ZoomIn, ZoomOut, RotateCcw, Trash2 } from "lucide-react";
import { useConfirm } from "@/hooks/useConfirm";

interface ZoomViewerProps {
  imageUrl: string;
  title?: string;
  onClose?: () => void;
  /** Suppression définitive de l'image inspectée (confirmation demandée ici).
   *  À charge de l'appelant de fermer le viewer ensuite. */
  onDelete?: () => void;
}

export function ZoomViewer({ imageUrl, title, onClose, onDelete }: ZoomViewerProps) {
  const confirm = useConfirm();

  const handleDelete = async () => {
    if (!onDelete) return;
    const ok = await confirm({
      title: "Supprimer ce résultat ?",
      description:
        "L'image source et le résultat seront définitivement supprimés du stockage. Cette action est irréversible.",
      confirmLabel: "Supprimer",
    });
    if (ok) onDelete();
  };

  return (
    <m.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ type: "spring", stiffness: 280, damping: 28 }}
      className="relative rounded-2xl overflow-hidden border border-border bg-black group"
    >
      {/* Bordure intérieure au hover */}
      <div className="absolute inset-0 rounded-2xl ring-1 ring-inset ring-primary/0 group-hover:ring-primary/25 transition-all duration-500 pointer-events-none z-30" />

      <TransformWrapper
        initialScale={1}
        minScale={0.5}
        maxScale={10}
        centerOnInit
        wheel={{ step: 0.15 }}
        doubleClick={{ disabled: false, mode: "zoomIn", step: 0.7 }}
      >
        {({ zoomIn, zoomOut, resetTransform }) => (
          <>
            {/* Toolbar flottante */}
            <m.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15, duration: 0.4 }}
              className="absolute top-4 right-4 z-20 flex items-center gap-0.5 p-1 rounded-lg bg-black/70 backdrop-blur-sm border border-white/10"
            >
              <m.button
                onClick={() => zoomIn()}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-white/10 transition-colors"
                title="Zoom avant"
              >
                <ZoomIn className="w-3.5 h-3.5" strokeWidth={2} />
              </m.button>
              <m.button
                onClick={() => zoomOut()}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-white/10 transition-colors"
                title="Zoom arrière"
              >
                <ZoomOut className="w-3.5 h-3.5" strokeWidth={2} />
              </m.button>
              <m.button
                onClick={() => resetTransform()}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-white/10 transition-colors"
                title="Réinitialiser"
              >
                <RotateCcw className="w-3.5 h-3.5" strokeWidth={2} />
              </m.button>
              {(onDelete || onClose) && <div className="w-px h-4 bg-white/20 mx-1" />}
              {onDelete && (
                <m.button
                  onClick={() => void handleDelete()}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  transition={{ type: "spring", stiffness: 400, damping: 25 }}
                  className="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-destructive/80 transition-colors"
                  title="Supprimer"
                  aria-label="Supprimer le résultat"
                >
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={2} />
                </m.button>
              )}
              {onClose && (
                <m.button
                  onClick={onClose}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  transition={{ type: "spring", stiffness: 400, damping: 25 }}
                  className="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-white/10 transition-colors"
                  aria-label="Fermer le viewer"
                >
                  <X className="w-3.5 h-3.5" strokeWidth={2} />
                </m.button>
              )}
            </m.div>

            {/* Titre flottant */}
            {title && (
              <m.div
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2, duration: 0.4 }}
                className="absolute top-4 left-4 z-20"
              >
                <span
                  data-tabular
                  className="text-[10px] font-mono uppercase tracking-[0.2em] px-2.5 py-1 rounded-md bg-black/70 text-white/85 backdrop-blur-sm border border-white/10"
                >
                  {title}
                </span>
              </m.div>
            )}

            <TransformComponent
              wrapperStyle={{ width: "100%", height: "600px" }}
              contentStyle={{
                width: "100%",
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <img
                src={imageUrl}
                alt={title ?? "Image"}
                className="max-w-full max-h-full object-contain"
                draggable={false}
              />
            </TransformComponent>
          </>
        )}
      </TransformWrapper>

      {/* Helper text en bas */}
      <m.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 0.4 }}
        className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20"
      >
        <span className="text-[9px] font-mono uppercase tracking-[0.2em] px-2.5 py-1 rounded-md bg-black/70 text-white/55 backdrop-blur-sm border border-white/10">
          Molette · Glisser · Double-clic
        </span>
      </m.div>
    </m.div>
  );
}
