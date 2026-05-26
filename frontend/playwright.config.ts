import { defineConfig, devices } from "@playwright/test";

/**
 * Configuration Playwright pour les tests E2E de GEGM Upscaler.
 *
 * Principe : on teste l'UI frontend en isolation — le backend `/api/*`
 * est intercepté via `page.route()` dans chaque spec (cf. `e2e/fixtures.ts`).
 * Aucun Postgres, Redis, Celery ou RunPod n'est requis pour exécuter
 * ces tests. Ça les rend rapides (~1 min pour toute la suite) et
 * stables en CI.
 *
 * Vite est démarré automatiquement par Playwright via `webServer` — pas
 * besoin d'avoir un process Vite déjà lancé manuellement.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",

  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    // En CI : on sert le build statique via `vite preview` (aucun file-watcher
    // → évite l'erreur EMFILE « too many open files » du dev server sur le
    // runner Kubernetes, dont la limite de file descriptors est basse). En
    // local : `vite dev` (HMR) pour le confort. Le build est produit en amont
    // (cf. before_script du job e2e dans .gitlab-ci.yml).
    command: process.env.CI
      ? "npm run preview -- --port 5173 --strictPort"
      : "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
