import { ReactCompareSlider, ReactCompareSliderImage } from "react-compare-slider";
import { X } from "lucide-react";

interface CompareSliderProps {
  beforeSrc: string;
  afterSrc: string;
  beforeLabel?: string;
  afterLabel?: string;
  onClose?: () => void;
}

export function CompareSlider({
  beforeSrc,
  afterSrc,
  beforeLabel = "Original",
  afterLabel = "Upscalé",
  onClose,
}: CompareSliderProps) {
  return (
    <div className="relative rounded-xl overflow-hidden border border-border bg-black">
      {/* Labels flottants */}
      <div className="absolute top-3 left-3 z-10">
        <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded-md bg-black/60 text-white/80 backdrop-blur-sm">
          {beforeLabel}
        </span>
      </div>
      <div className="absolute top-3 right-3 z-10">
        <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded-md bg-primary/80 text-white backdrop-blur-sm">
          {afterLabel}
        </span>
      </div>

      {onClose && (
        <button
          onClick={onClose}
          className="absolute top-3 left-1/2 -translate-x-1/2 z-20 p-1.5 rounded-lg bg-black/60 text-white/70 hover:text-white hover:bg-black/80 backdrop-blur-sm transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      )}

      <ReactCompareSlider
        itemOne={
          <ReactCompareSliderImage
            src={beforeSrc}
            alt="Image originale"
            className="object-contain"
          />
        }
        itemTwo={
          <ReactCompareSliderImage
            src={afterSrc}
            alt="Image upscalée"
            className="object-contain"
          />
        }
        className="h-[500px]"
        style={{
          borderRadius: "inherit",
        }}
      />
    </div>
  );
}
