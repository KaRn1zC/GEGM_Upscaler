import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ImageUp, Clock, Sparkles, Layers, GalleryHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { UpscalePage } from "@/pages/UpscalePage";
import { BatchPage } from "@/pages/BatchPage";
import { GalleryPage } from "@/pages/GalleryPage";
import { HistoryPage } from "@/pages/HistoryPage";

const NAV_ITEMS = [
  { to: "/upscale", label: "Upscaler", icon: ImageUp },
  { to: "/batch", label: "Batch", icon: Layers },
  { to: "/gallery", label: "Galerie", icon: GalleryHorizontal },
  { to: "/history", label: "Historique", icon: Clock },
];

function Sidebar() {
  return (
    <aside className="w-56 shrink-0 border-r border-border bg-card/50 flex flex-col">
      {/* Logo */}
      <div className="p-5 flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-primary/15 flex items-center justify-center">
          <Sparkles className="w-4 h-4 text-primary" />
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground leading-none">GEGM</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">Upscaler</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-0.5">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                isActive
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
              )
            }
          >
            <Icon className="w-4 h-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Pied */}
      <div className="p-4 border-t border-border">
        <p className="text-[10px] text-muted-foreground/60 font-mono">v0.1.0</p>
      </div>
    </aside>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-dvh overflow-hidden bg-background">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/upscale" element={<UpscalePage />} />
            <Route path="/batch" element={<BatchPage />} />
            <Route path="/gallery" element={<GalleryPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="*" element={<Navigate to="/upscale" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
