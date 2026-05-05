import { useEffect, useState } from "react";
import { m } from "motion/react";
import {
  Check,
  Globe,
  Loader2,
  LogOut,
  RefreshCw,
  Server,
  Sparkles,
  User,
  Wrench,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { getCurrentUser, getReadiness } from "@/lib/api";
import type { HealthResponse, UserResponse } from "@/lib/api";
import { SCALE_FACTORS, SCALE_TO_MODEL, type ScaleFactor } from "@/lib/constants";
import { usePreferences } from "@/hooks/usePreferences";
import { useAuth } from "@/hooks/useAuth";
import { useUpdaterStore } from "@/stores/useUpdaterStore";
import { isTauri } from "@/lib/tauri";
import { cn } from "@/lib/utils";

const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const;

export function SettingsPage() {
  const { t } = useTranslation();
  const { preferences, updatePreference, resetPreferences } = usePreferences();
  const { logout, authMode } = useAuth();
  const updater = useUpdaterStore();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [userError, setUserError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [userRes, healthRes] = await Promise.allSettled([
          getCurrentUser(),
          getReadiness(),
        ]);

        if (userRes.status === "fulfilled") {
          setUser(userRes.value);
        } else {
          setUserError(userRes.reason instanceof Error ? userRes.reason.message : "Erreur");
        }

        if (healthRes.status === "fulfilled") {
          setHealth(healthRes.value);
        }
      } finally {
        setLoading(false);
      }
    };
    void fetchData();
  }, []);

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* Halo subtil en haut */}
      <div className="absolute inset-x-0 top-0 h-80 bg-gradient-to-b from-primary/[0.06] to-transparent pointer-events-none" />

      <div className="relative z-10 p-6 lg:p-12 max-w-3xl mx-auto w-full">
        {/* En-tête */}
        <m.header
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO }}
          className="mb-10"
        >
          <h1 className="font-display font-light text-5xl lg:text-7xl tracking-tight text-foreground leading-[0.95]">
            Paramètres
          </h1>
          <p className="mt-4 text-[11px] uppercase tracking-[0.3em] text-muted-foreground font-sans">
            Préférences utilisateur et état du système
          </p>
        </m.header>

      {/* Utilisateur */}
      <Section icon={User} title="Compte">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Chargement...
          </div>
        ) : user ? (
          <div className="space-y-2 text-sm">
            <Row label="Email" value={user.email} mono />
            <Row label="Nom" value={user.name ?? "—"} />
            <Row
              label="Créé le"
              value={new Date(user.created_at).toLocaleDateString("fr-FR", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            />
            <Row label="ID" value={user.id} mono muted />
          </div>
        ) : (
          <p className="text-sm text-destructive/80">
            Impossible de récupérer l'utilisateur : {userError}
          </p>
        )}

        {authMode === "oidc" && (
          <div className="mt-5 pt-4 border-t border-border/60">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <p className="text-xs text-muted-foreground max-w-sm">
                {t("settings.logoutHint")}
              </p>
              <button
                onClick={() => logout({ redirectToIdp: true })}
                className={cn(
                  "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors",
                  "border-border text-muted-foreground hover:text-destructive hover:border-destructive/50",
                )}
              >
                <LogOut className="w-3.5 h-3.5" strokeWidth={2} />
                {t("settings.logout")}
              </button>
            </div>
          </div>
        )}
      </Section>

      {/* Préférences */}
      <Section icon={Wrench} title="Préférences">
        <div className="space-y-5">
          {/* Facteur par défaut */}
          <div>
            <label className="text-xs text-muted-foreground uppercase tracking-wider block mb-2">
              Facteur d'upscaling par défaut
            </label>
            <div className="inline-flex items-center gap-1 bg-muted rounded-lg p-0.5">
              {SCALE_FACTORS.map((f) => (
                <button
                  key={f}
                  onClick={() => updatePreference("defaultScaleFactor", f as ScaleFactor)}
                  className={cn(
                    "text-xs px-4 py-1.5 rounded-md font-medium transition-all",
                    preferences.defaultScaleFactor === f
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {f}&times;
                </button>
              ))}
            </div>
          </div>

          {/* Routage scale → modèle (info seule) */}
          <div>
            <label className="text-xs text-muted-foreground uppercase tracking-wider block mb-2">
              Modèles utilisés
            </label>
            <div className="text-xs text-muted-foreground space-y-1 font-mono">
              <p>
                <span className="text-foreground">×2</span> →{" "}
                {SCALE_TO_MODEL[2].label}
              </p>
              <p>
                <span className="text-foreground">×4</span> →{" "}
                {SCALE_TO_MODEL[4].label}
              </p>
            </div>
          </div>

          {/* Reset */}
          <div className="pt-2">
            <button
              onClick={resetPreferences}
              className="text-xs text-muted-foreground hover:text-destructive transition-colors"
            >
              Réinitialiser aux valeurs par défaut
            </button>
          </div>
        </div>
      </Section>

      {/* Langue */}
      <Section icon={Globe} title={t("settings.language")}>
        <LanguageSwitcher />
      </Section>

      {/* État du système */}
      <Section icon={Server} title="État du système">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Chargement...
          </div>
        ) : health ? (
          <div className="space-y-2">
            <HealthRow label="Statut global" status={health.status === "ready" ? "ok" : "error"} />
            {health.checks &&
              Object.entries(health.checks).map(([name, value]) => (
                <HealthRow
                  key={name}
                  label={name.charAt(0).toUpperCase() + name.slice(1)}
                  status={value === "ok" ? "ok" : "error"}
                  detail={value !== "ok" ? value : undefined}
                />
              ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Aucune information disponible</p>
        )}
      </Section>

        {/* Mises à jour — visible uniquement dans Tauri */}
        {isTauri() && (
          <Section icon={Sparkles} title="Mises à jour">
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="text-xs text-muted-foreground">
                  {updater.phase === "checking" && "Vérification en cours…"}
                  {updater.phase === "available" && updater.update && (
                    <>
                      <span className="text-primary font-medium">
                        Nouvelle version disponible :
                      </span>{" "}
                      <span className="font-mono">v{updater.update.version}</span>
                    </>
                  )}
                  {updater.phase === "idle" && updater.checkedOnce && (
                    <>Aucune mise à jour disponible — tu es à jour.</>
                  )}
                  {updater.phase === "idle" && !updater.checkedOnce && (
                    <>Cliquer pour vérifier manuellement les mises à jour.</>
                  )}
                  {updater.phase === "downloading" && "Téléchargement…"}
                  {updater.phase === "installing" && "Installation…"}
                  {updater.phase === "error" && (
                    <span className="text-destructive/80">
                      Erreur : {updater.error}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => void updater.checkNow()}
                  disabled={updater.phase === "checking" || updater.phase === "downloading"}
                  className={cn(
                    "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors",
                    "border-border text-muted-foreground hover:text-foreground hover:border-primary/40",
                    "disabled:opacity-50 disabled:cursor-not-allowed",
                  )}
                >
                  <RefreshCw
                    className={cn(
                      "w-3.5 h-3.5",
                      updater.phase === "checking" && "animate-spin",
                    )}
                    strokeWidth={2}
                  />
                  Vérifier maintenant
                </button>
              </div>
            </div>
          </Section>
        )}

        {/* Infos build */}
        <Section icon={Wrench} title="À propos">
          <div className="space-y-2 text-sm">
            <Row label="Version" value="0.1.0" mono />
            <Row label="Modèle SR" value="DRCT-L (fallback HAT-L)" />
            <Row label="Stack" value="FastAPI · React 19 · Tauri 2" muted />
          </div>
        </Section>
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────

interface SectionProps {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}

function Section({ icon: Icon, title, children }: SectionProps) {
  return (
    <section className="mb-6 rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-4 h-4 text-muted-foreground" />
        <h2 className="text-sm font-medium text-foreground">{title}</h2>
      </div>
      {children}
    </section>
  );
}

interface RowProps {
  label: string;
  value: string;
  mono?: boolean;
  muted?: boolean;
}

function Row({ label, value, mono, muted }: RowProps) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={cn(
          "text-xs truncate",
          mono && "font-mono",
          muted ? "text-muted-foreground" : "text-foreground",
        )}
      >
        {value}
      </span>
    </div>
  );
}

interface HealthRowProps {
  label: string;
  status: "ok" | "error";
  detail?: string;
}

function HealthRow({ label, status, detail }: HealthRowProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex items-center gap-2">
        {status === "ok" ? (
          <Check className="w-3.5 h-3.5 text-success" />
        ) : (
          <X className="w-3.5 h-3.5 text-destructive" />
        )}
        <span className="text-xs text-foreground">{label}</span>
      </div>
      {detail && (
        <span className="text-xs font-mono text-destructive/70 truncate max-w-xs">{detail}</span>
      )}
    </div>
  );
}
