import * as Sentry from "@sentry/react";

/**
 * Initialise le SDK Sentry côté React/Tauri.
 *
 * No-op si `VITE_SENTRY_DSN` est vide (mode dev local ou build sans
 * observability). En prod, le DSN est injecté au build-time par le
 * Dockerfile (image web) ou par le workflow `release-tauri.yml` (bundle
 * desktop), pointant vers l'instance self-hosted `errors.vixns.net`.
 *
 * `release` et `environment` aident à trier les erreurs par version et
 * par contexte d'exécution (prod web, prod Tauri, staging, etc.).
 */
export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) {
    return;
  }

  Sentry.init({
    dsn,
    release: import.meta.env.VITE_APP_VERSION || "dev",
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || import.meta.env.MODE,
    integrations: [Sentry.browserTracingIntegration()],
    // Échantillonnage 10 % — assez pour tracer les golden paths sans
    // saturer l'instance self-hosted. À ajuster selon le volume réel.
    tracesSampleRate: 0.1,
    // Filtrage des bruits connus du runtime Tauri/WKWebView qui ne
    // remontent rien d'actionnable.
    ignoreErrors: [
      "ResizeObserver loop limit exceeded",
      "ResizeObserver loop completed with undelivered notifications",
      "Non-Error promise rejection captured",
    ],
  });
}
