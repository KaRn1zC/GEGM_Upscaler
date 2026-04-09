import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import { X, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";

interface ZoomViewerProps {
  imageUrl: string;
  title?: string;
  onClose?: () => void;
}

export function ZoomViewer({ imageUrl, title, onClose }: ZoomViewerProps) {
  return (
    <div className="relative rounded-xl overflow-hidden border border-border bg-black">
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
            {/* Barre d'outils flottante */}
            <div className="absolute top-3 right-3 z-10 flex items-center gap-1 p-1 rounded-lg bg-black/60 backdrop-blur-sm">
              <button
                onClick={() => zoomIn()}
                className="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-white/10 transition-colors"
                title="Zoom avant"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => zoomOut()}
                className="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-white/10 transition-colors"
                title="Zoom arrière"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => resetTransform()}
                className="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-white/10 transition-colors"
                title="Réinitialiser"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
              {onClose && (
                <>
                  <div className="w-px h-4 bg-white/20 mx-0.5" />
                  <button
                    onClick={onClose}
                    className="p-1.5 rounded-md text-white/80 hover:text-white hover:bg-white/10 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </>
              )}
            </div>

            {/* Titre flottant */}
            {title && (
              <div className="absolute top-3 left-3 z-10">
                <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded-md bg-black/60 text-white/80 backdrop-blur-sm">
                  {title}
                </span>
              </div>
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

      {/* Indication d'usage */}
      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-black/60 text-[10px] font-mono text-white/60 backdrop-blur-sm">
        Molette : zoom · Glisser : pan · Double-clic : zoom avant
      </div>
    </div>
  );
}
