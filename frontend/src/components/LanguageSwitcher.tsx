import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

/**
 * Sélecteur de langue — bascule entre fr/en via i18next.
 * Persiste automatiquement dans ``localStorage.i18nextLng``.
 *
 * Design : deux boutons radio-like pour se fondre dans les sections
 * `SettingsPage` plutôt qu'un `<select>` natif qui casserait l'esthétique.
 */
export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const current = i18n.resolvedLanguage ?? "fr";

  const languages = [
    { code: "fr", label: t("settings.languageFr") },
    { code: "en", label: t("settings.languageEn") },
  ] as const;

  return (
    <div className="flex gap-2">
      {languages.map(({ code, label }) => (
        <button
          key={code}
          type="button"
          onClick={() => void i18n.changeLanguage(code)}
          className={cn(
            "px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
            current === code
              ? "bg-primary text-primary-foreground glow-sm"
              : "bg-card border border-border text-muted-foreground hover:text-foreground",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
