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
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
