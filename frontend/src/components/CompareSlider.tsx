import { m } from "motion/react";
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
    <m.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ type: "spring", stiffness: 280, damping: 28 }}
      className="relative rounded-2xl overflow-hidden border border-border bg-black group"
    >
      {/* Bordure intérieure bleu électrique au hover */}
      <div className="absolute inset-0 rounded-2xl ring-1 ring-inset ring-primary/0 group-hover:ring-primary/30 transition-all duration-500 pointer-events-none z-30" />

      {/* Labels flottants avec entrée staggered */}
      <m.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.15, duration: 0.4 }}
        className="absolute top-4 left-4 z-20"
      >
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] px-2.5 py-1 rounded-md bg-black/70 text-white/85 backdrop-blur-sm border border-white/10">
          {beforeLabel}
        </span>
      </m.div>
      <m.div
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.15, duration: 0.4 }}
        className="absolute top-4 right-4 z-20"
      >
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] px-2.5 py-1 rounded-md bg-primary/90 text-primary-foreground backdrop-blur-sm glow-sm">
          {afterLabel}
        </span>
      </m.div>

      {onClose && (
        <m.button
          onClick={onClose}
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.92 }}
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, type: "spring", stiffness: 400, damping: 25 }}
          className="absolute top-4 left-1/2 -translate-x-1/2 z-30 p-2 rounded-lg bg-black/70 text-white/80 hover:text-white hover:bg-black/90 backdrop-blur-sm border border-white/10 transition-colors"
          aria-label="Fermer la comparaison"
        >
          <X className="w-4 h-4" />
        </m.button>
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

      {/* Helper text en bas */}
      <m.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 0.4 }}
        className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20"
      >
        <span className="text-[9px] font-mono uppercase tracking-[0.2em] px-2.5 py-1 rounded-md bg-black/70 text-white/55 backdrop-blur-sm border border-white/10">
          Glisser pour comparer
        </span>
      </m.div>
    </m.div>
  );
}
