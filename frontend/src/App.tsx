import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { lazy, Suspense, type ReactNode } from "react";
import { LazyMotion, domMax, m, AnimatePresence } from "motion/react";
import {
  ImageUp,
  Clock,
  Layers,
  GalleryHorizontal,
  Settings,
  Command as CommandIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { CapabilityBadge } from "@/components/CapabilityBadge";
import { ConfirmProvider } from "@/components/ConfirmProvider";
import { UpdateBanner } from "@/components/UpdateBanner";
import { useAuth } from "@/hooks/useAuth";
import { useGlobalShortcuts } from "@/hooks/useGlobalShortcuts";
import { useJobNotifications } from "@/hooks/useJobNotifications";

// Pages lazy-loadées — chacune devient son propre chunk Vite. Réduit le
// bundle initial à la page courante uniquement (la nav précharge à la
// demande via le router).
const UpscalePage = lazy(() =>
  import("@/pages/UpscalePage").then((m) => ({ default: m.UpscalePage })),
);
const BatchPage = lazy(() =>
  import("@/pages/BatchPage").then((m) => ({ default: m.BatchPage })),
);
const GalleryPage = lazy(() =>
  import("@/pages/GalleryPage").then((m) => ({ default: m.GalleryPage })),
);
const HistoryPage = lazy(() =>
  import("@/pages/HistoryPage").then((m) => ({ default: m.HistoryPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
const LoginPage = lazy(() =>
  import("@/pages/LoginPage").then((m) => ({ default: m.LoginPage })),
);
const AuthCallbackPage = lazy(() =>
  import("@/pages/AuthCallbackPage").then((m) => ({ default: m.AuthCallbackPage })),
);

// Code-split — la command palette (+ cmdk + radix-dialog) est chargée à
// la demande dans son propre chunk, pas dans le bundle initial.
const CommandPalette = lazy(() => import("@/components/CommandPalette"));

// Les `labelKey` sont résolues côté composant via `t()` — on les garde en
// table statique pour préserver le bundle-splitting de la nav.
const NAV_ITEMS = [
  { to: "/upscale", labelKey: "nav.upscaler", icon: ImageUp, shortcut: "⌘1" },
  { to: "/batch", labelKey: "nav.batch", icon: Layers, shortcut: "⌘2" },
  { to: "/gallery", labelKey: "nav.gallery", icon: GalleryHorizontal, shortcut: "⌘3" },
  { to: "/history", labelKey: "nav.history", icon: Clock, shortcut: "⌘4" },
  { to: "/settings", labelKey: "nav.settings", icon: Settings, shortcut: "⌘5" },
] as const;

const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;

function Sidebar() {
  const { t } = useTranslation();
  return (
    <aside className="relative w-60 shrink-0 border-r border-border bg-card/30 backdrop-blur-sm flex flex-col">
      {/* Gradient subtil derrière le logo */}
      <div className="absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.08] to-transparent pointer-events-none" />

      {/* Logo GEGM — Fraunces serif contraste extrême */}
      <m.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: EASE_OUT_EXPO }}
        className="relative p-6 pb-5"
      >
        <h1 className="font-display font-light text-3xl text-foreground leading-none tracking-tight">
          GEGM
        </h1>
        <p
          className="mt-1.5 text-[9px] font-sans uppercase tracking-[0.3em] text-muted-foreground"
          style={{ textIndent: "-0.15em" }}
        >
          Upscaler
        </p>
      </m.div>

      {/* Séparateur fin */}
      <div className="mx-6 h-px bg-border" />

      {/* Navigation */}
      <nav className="relative flex-1 px-3 py-5">
        {NAV_ITEMS.map(({ to, labelKey, icon: Icon, shortcut }, i) => (
          <m.div
            key={to}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{
              delay: 0.15 + i * 0.04,
              duration: 0.5,
              ease: EASE_OUT_EXPO,
            }}
          >
            <NavLink to={to} end>
              {({ isActive }) => (
                <div
                  className={cn(
                    "relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors group",
                    isActive
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {/* Indicateur actif — glisse entre les items via layoutId */}
                  {isActive && (
                    <m.div
                      layoutId="nav-indicator"
                      className="absolute inset-0 bg-primary/10 border border-primary/30 rounded-lg glow-sm"
                      transition={{
                        type: "spring",
                        stiffness: 400,
                        damping: 32,
                      }}
                    />
                  )}
                  <Icon
                    className="relative w-4 h-4 shrink-0"
                    strokeWidth={1.8}
                  />
                  <span className="relative font-medium flex-1">{t(labelKey)}</span>
                  <span
                    className={cn(
                      "relative text-[9px] font-mono opacity-0 group-hover:opacity-60 transition-opacity",
                      isActive && "opacity-50",
                    )}
                  >
                    {shortcut}
                  </span>
                </div>
              )}
            </NavLink>
          </m.div>
        ))}
      </nav>

      {/* Capability badge + hint palette + version */}
      <m.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5, duration: 0.6 }}
        className="relative p-4 border-t border-border space-y-3"
      >
        <div className="flex justify-center">
          <CapabilityBadge />
        </div>
        <div className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-card/60 border border-border/60">
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <CommandIcon className="w-3 h-3" strokeWidth={2} />
            <span className="uppercase tracking-[0.15em]">{t("nav.palette")}</span>
          </div>
          <kbd className="text-[9px] font-mono text-muted-foreground/70 px-1.5 py-0.5 rounded border border-border/60 bg-background/40">
            ⌘K
          </kbd>
        </div>
        <p
          data-tabular
          className="text-[9px] font-mono uppercase tracking-[0.2em] text-muted-foreground/60 px-1"
        >
          v0.1.0
        </p>
      </m.div>
    </aside>
  );
}

/**
 * Wrapper qui redirige vers /login si l'utilisateur n'est pas authentifié.
 * En mode `dev`, `isAuthenticated` est toujours `true` → transparent.
 * En mode `oidc`, redirige sur /login tant que le user n'a pas de tokens.
 */
function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/**
 * Routes protégées + sidebar — affichées seulement quand authentifié.
 */
function AuthenticatedApp() {
  const location = useLocation();

  // Active les raccourcis clavier globaux ⌘1..⌘5 / ⌘U / ⌘B.
  useGlobalShortcuts();

  // Diffuse les notifications macOS natives sur completion/échec des jobs
  // (no-op hors runtime Tauri).
  useJobNotifications();

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      <Sidebar />
      <main className="flex-1 overflow-y-auto relative">
        <AnimatePresence mode="wait" initial={false}>
          <m.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.32, ease: EASE_OUT_EXPO }}
            className="h-full"
          >
            <Suspense fallback={null}>
              <Routes location={location}>
                <Route path="/upscale" element={<UpscalePage />} />
                <Route path="/batch" element={<BatchPage />} />
                <Route path="/gallery" element={<GalleryPage />} />
                <Route path="/history" element={<HistoryPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<Navigate to="/upscale" replace />} />
              </Routes>
            </Suspense>
          </m.div>
        </AnimatePresence>
      </main>
      <Suspense fallback={null}>
        <CommandPalette />
      </Suspense>
      <UpdateBanner />
    </div>
  );
}

export default function App() {
  return (
    <LazyMotion features={domMax} strict>
      <ConfirmProvider>
        <BrowserRouter>
          <Suspense fallback={null}>
            <Routes>
            {/* Routes publiques (hors RequireAuth) */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/auth/callback" element={<AuthCallbackPage />} />
            {/* Reste de l'app protégé par auth */}
              <Route
                path="/*"
                element={
                  <RequireAuth>
                    <AuthenticatedApp />
                  </RequireAuth>
                }
              />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ConfirmProvider>
    </LazyMotion>
  );
}
