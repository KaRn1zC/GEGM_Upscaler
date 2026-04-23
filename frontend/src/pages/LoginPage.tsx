import { m } from "motion/react";
import { LogIn, Sparkles } from "lucide-react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/useAuth";

const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;

/**
 * Écran de connexion — affiché uniquement en mode OIDC pour les users
 * non authentifiés. En mode `dev`, un RequireAuth autoredirige vers
 * /upscale sans passer par ici.
 */
export function LoginPage() {
  const { t } = useTranslation();
  const { isAuthenticated, login, authMode } = useAuth();

  if (isAuthenticated) {
    return <Navigate to="/upscale" replace />;
  }

  // Sécurité : la page login ne doit jamais apparaître en mode dev —
  // si on arrive ici, c'est un bug de config, on redirige.
  if (authMode === "dev") {
    return <Navigate to="/upscale" replace />;
  }

  return (
    <div className="relative flex-1 min-h-screen flex items-center justify-center overflow-hidden bg-background">
      {/* Background gradient mesh signature GEGM */}
      <div className="absolute inset-0 gradient-mesh opacity-70 pointer-events-none" />
      <div className="absolute inset-0 bg-gradient-to-b from-surface-deep/40 via-transparent to-transparent pointer-events-none" />

      <m.div
        initial={{ opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.9, ease: EASE_OUT_EXPO }}
        className="relative z-10 w-full max-w-md px-8 py-12"
      >
        {/* Logo GEGM */}
        <m.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.15, ease: EASE_OUT_EXPO }}
          className="mb-10 text-center"
        >
          <h1 className="font-display font-light text-6xl text-foreground leading-none tracking-tight">
            GEGM
          </h1>
          <p className="mt-3 text-[10px] font-sans uppercase tracking-[0.3em] text-muted-foreground">
            Upscaler
          </p>
        </m.div>

        {/* Carte login */}
        <m.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.3, ease: EASE_OUT_EXPO }}
          className="relative rounded-2xl border border-border bg-card/60 backdrop-blur-sm p-8"
        >
          <div className="absolute top-6 right-6 text-primary/60">
            <Sparkles className="w-4 h-4" strokeWidth={1.5} />
          </div>

          <h2 className="font-display font-light text-2xl text-foreground leading-tight">
            {t("auth.loginRequired")}
          </h2>
          <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
            {t("auth.loginDescription")}
          </p>

          <m.button
            onClick={() => void login()}
            whileHover={{ scale: 1.02, y: -1 }}
            whileTap={{ scale: 0.98 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            className="mt-8 w-full flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl bg-primary text-primary-foreground font-medium text-sm tracking-wide glow-md hover:glow-lg transition-shadow"
          >
            <LogIn className="w-4 h-4" strokeWidth={2} />
            {t("auth.loginButton")}
          </m.button>

          <p className="mt-6 text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground/70 text-center">
            {t("auth.loginFooter")}
          </p>
        </m.div>

        {/* Footer version */}
        <m.p
          data-tabular
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.6 }}
          transition={{ duration: 0.6, delay: 0.6 }}
          className="mt-8 text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground/60 text-center"
        >
          v0.1.0
        </m.p>
      </m.div>
    </div>
  );
}
