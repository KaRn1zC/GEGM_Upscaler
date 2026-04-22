import { test as base, type Page, type Route } from "@playwright/test";

/**
 * Fabrique un objet `Job` compatible avec `JobResponse` du backend, avec
 * des valeurs par défaut cohérentes. Les tests écrasent les champs utiles.
 */
export function makeJob(overrides: Partial<JobResponse> = {}): JobResponse {
  const id = overrides.id ?? `job-${Math.random().toString(36).slice(2, 10)}`;
  const now = "2026-04-22T12:00:00Z";
  return {
    id,
    user_id: "user-test",
    status: "completed",
    input_key: `uploads/${id}.png`,
    output_key: `results/${id}.png`,
    scale_factor: 4,
    model_name: "drct-l",
    input_width: 1000,
    input_height: 800,
    output_width: 4000,
    output_height: 3200,
    gpu_backend: "cloud",
    progress: 1,
    error_message: null,
    prefer_local: null,
    created_at: now,
    updated_at: now,
    completed_at: now,
    ...overrides,
  };
}

export interface JobResponse {
  id: string;
  user_id: string;
  status: string;
  input_key: string;
  output_key: string | null;
  scale_factor: number;
  model_name: string;
  input_width: number;
  input_height: number;
  output_width: number | null;
  output_height: number | null;
  gpu_backend: string | null;
  progress: number;
  error_message: string | null;
  prefer_local: boolean | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

interface ApiMocks {
  /** Jobs retournés par `GET /api/jobs`. Les tests peuvent les muter. */
  jobs: JobResponse[];
  /** Installe les routes par défaut. Les tests peuvent les override ensuite. */
  install: (page: Page) => Promise<void>;
  /**
   * Renvoie un PNG rouge 1×1 minimal pour les endpoints qui servent
   * des images (download, preview uploads) — évite de charger des
   * vraies images en test.
   */
  tinyPng: () => Buffer;
}

// PNG rouge 1×1 (67 bytes) — plus petit valid PNG possible.
const TINY_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==";

/**
 * Fixture Playwright qui expose `apiMocks` dans chaque test. Installation
 * par défaut au début du test — les specs peuvent surcharger via
 * `page.route()` direct pour les cas spéciaux (erreur 500, SSE stream, etc.).
 *
 * Notes ESLint :
 *   - `no-empty-pattern` : Playwright impose une destructuration d'objet
 *     comme 1er arg de la fixture. Comme on n'utilise aucun fixture built-in
 *     (page, browser…), on destructure `{}` vide — c'est le pattern
 *     officiellement supporté par Playwright.
 *   - `react-hooks/rules-of-hooks` : le callback `use` de Playwright n'est
 *     pas un React hook, mais ESLint l'interprète comme tel à cause du nom.
 */
/* eslint-disable no-empty-pattern, react-hooks/rules-of-hooks --
   Playwright fixture API — cf. docstring ci-dessus */
export const test = base.extend<{ apiMocks: ApiMocks }>({
  apiMocks: async ({}, use) => {
    const state: ApiMocks = {
      jobs: [],
      tinyPng: () => Buffer.from(TINY_PNG_B64, "base64"),
      install: async (page: Page) => {
        // GET /api/jobs — liste des jobs
        await page.route(/\/api\/jobs(\?.*)?$/, async (route: Route) => {
          if (route.request().method() === "GET") {
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify(state.jobs),
            });
          } else {
            await route.continue();
          }
        });

        // GET /api/jobs/{id} — détail d'un job
        await page.route(/\/api\/jobs\/[^/?]+(\?.*)?$/, async (route: Route) => {
          const url = new URL(route.request().url());
          const id = url.pathname.split("/").pop();
          if (route.request().method() === "GET") {
            const job = state.jobs.find((j) => j.id === id);
            if (job) {
              await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(job),
              });
            } else {
              await route.fulfill({ status: 404 });
            }
          } else if (route.request().method() === "DELETE") {
            state.jobs = state.jobs.filter((j) => j.id !== id);
            await route.fulfill({ status: 204 });
          } else {
            await route.continue();
          }
        });

        // GET /api/users/me — profil utilisateur
        await page.route(/\/api\/users\/me(\?.*)?$/, async (route: Route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              id: "user-test",
              email: "test@gegm.local",
              name: "Test User",
              created_at: "2026-01-01T00:00:00Z",
            }),
          });
        });

        // GET /api/health[/ready] — état du système
        await page.route(/\/api\/health(\/ready)?(\?.*)?$/, async (route: Route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              status: "ready",
              checks: { db: "ok", redis: "ok" },
            }),
          });
        });

        // GET /api/jobs/{id}/download + /api/uploads/* — images
        await page.route(
          /\/api\/(jobs\/[^/]+\/download|uploads\/.+)(\?.*)?$/,
          async (route: Route) => {
            await route.fulfill({
              status: 200,
              contentType: "image/png",
              body: state.tinyPng(),
            });
          },
        );

        // GET /api/jobs/{id}/progress — stream SSE — default no-op (200 vide).
        // Les tests de flow upscale override cette route avec un vrai stream.
        await page.route(/\/api\/jobs\/[^/]+\/progress(\?.*)?$/, async (route: Route) => {
          await route.fulfill({
            status: 200,
            contentType: "text/event-stream",
            body: "",
          });
        });
      },
    };

    await use(state);
  },
});

export { expect } from "@playwright/test";
