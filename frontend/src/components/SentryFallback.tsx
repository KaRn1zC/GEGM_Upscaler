import { useTranslation } from "react-i18next";

/**
 * Fallback UI affichée quand une erreur remonte jusqu'au `Sentry.ErrorBoundary`
 * racine (render/lifecycle crash). L'erreur est déjà envoyée à Sentry via le
 * boundary — ici on offre juste une sortie utilisable à l'utilisateur.
 *
 * Dans un fichier séparé plutôt qu'inline dans `main.tsx` pour laisser
 * React Fast Refresh fonctionner sur l'entrypoint.
 */
export function SentryFallback({ resetError }: { resetError: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4 bg-background px-6 text-center">
      <h1 className="font-display text-3xl font-light text-foreground">
        {t("fallback.title")}
      </h1>
      <p className="max-w-md text-sm text-muted-foreground">
        {t("fallback.description")}
      </p>
      <button
        type="button"
        onClick={resetError}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        {t("fallback.retry")}
      </button>
    </div>
  );
}
