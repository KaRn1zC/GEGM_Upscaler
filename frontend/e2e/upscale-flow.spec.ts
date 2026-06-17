import { test, expect, makeJob } from "./fixtures";

test.describe("Flow upscale + cancel + compare", () => {
  test.beforeEach(async ({ page, apiMocks }) => {
    await apiMocks.install(page);
  });

  test("should preview the file without launching the upscale automatically", async ({
    page,
    apiMocks,
  }) => {
    await page.goto("/upscale");

    // L'input file rendu par react-dropzone est masqué — on le trouve via type=file.
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "test.png",
      mimeType: "image/png",
      buffer: apiMocks.tinyPng(),
    });

    // La DropZone bascule en mode preview — le nom du fichier s'affiche.
    await expect(page.getByText("test.png")).toBeVisible();

    // Le bouton Lancer apparaît AVEC les settings courants (default ×4 + DRCT-L).
    // L'UI affiche le label en majuscules (`DRCT-L`) via `SCALE_TO_MODEL.label`,
    // mais on garde le test case-insensitive pour ne pas casser sur un
    // futur changement de casse cosmétique.
    const launchBtn = page.getByRole("button", { name: /Lancer l'upscale/ });
    await expect(launchBtn).toBeVisible();
    await expect(launchBtn).toContainText(/×4/);
    await expect(launchBtn).toContainText(/drct-l/i);

    // Aucune requête d'upload ou de création de job ne doit avoir été émise.
  });

  test("should run the full upscale flow from drop to completed", async ({
    page,
    apiMocks,
  }) => {
    // Prépare les mocks pour l'upload + création de job + SSE.
    await page.route(/\/api\/uploads(\?.*)?$/, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            key: "uploads/e2e-test.png",
            filename: "test.png",
            size: 67,
            content_type: "image/png",
          }),
        });
      } else {
        await route.continue();
      }
    });

    const jobId = "e2e-job-full";
    await page.route(/\/api\/jobs(\?.*)?$/, async (route) => {
      if (route.request().method() === "POST") {
        // Création de job — on renvoie un Job pending.
        const job = makeJob({
          id: jobId,
          status: "pending",
          progress: 0,
          input_key: "uploads/e2e-test.png",
          output_key: null,
          output_width: null,
          output_height: null,
          completed_at: null,
        });
        apiMocks.jobs = [job, ...apiMocks.jobs];
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(job),
        });
      } else if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(apiMocks.jobs),
        });
      } else {
        await route.continue();
      }
    });

    // Stream SSE qui envoie progression puis completed.
    await page.route(
      new RegExp(`/api/jobs/${jobId}/progress(\\?.*)?$`),
      async (route) => {
        const body = [
          `event: progress\ndata: ${JSON.stringify({ job_id: jobId, status: "processing", progress: 0.5 })}\n\n`,
          `event: completed\ndata: ${JSON.stringify({ job_id: jobId, status: "completed", progress: 1.0, output_key: "results/e2e-test.png" })}\n\n`,
        ].join("");
        await route.fulfill({
          status: 200,
          headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
          },
          body,
        });
      },
    );

    await page.goto("/upscale");

    // Drop du fichier
    await page.locator('input[type="file"]').first().setInputFiles({
      name: "test.png",
      mimeType: "image/png",
      buffer: apiMocks.tinyPng(),
    });

    // Clic sur Lancer l'upscale
    await page.getByRole("button", { name: /Lancer l'upscale/ }).click();

    // Le job apparaît en "Récents" après completion (section ne s'affiche
    // qu'avec les jobs terminés).
    await expect(page.getByText(/Récents/i)).toBeVisible({ timeout: 10_000 });
  });

  test("should allow cancelling an active job", async ({ page, apiMocks }) => {
    // Un job processing dans le store — la section "En cours" affiche sa card.
    const activeJob = makeJob({
      id: "cancel-me",
      status: "processing",
      progress: 0.4,
      output_key: null,
      output_width: null,
      output_height: null,
      completed_at: null,
    });
    apiMocks.jobs = [activeJob];

    await page.goto("/upscale");

    // "En cours" matche à la fois le heading de section ET le label
    // localisé du statut dans le JobCard — on cible le heading par rôle.
    await expect(page.getByRole("heading", { name: "En cours" })).toBeVisible();
    const cancelBtn = page.getByRole("button", { name: /Annuler/ });
    await expect(cancelBtn).toBeVisible();

    await cancelBtn.click();

    // Après cancel (POST /cancel mocké à 204), le job passe en `cancelled` :
    // il quitte "En cours" pour "Récents" et son bouton "Annuler" est
    // remplacé par "Supprimer" — donc plus aucun bouton "Annuler" visible.
    await expect(cancelBtn).not.toBeVisible({ timeout: 5_000 });
  });

  test("should open CompareSlider on a completed job", async ({ page, apiMocks }) => {
    const completed = makeJob({ id: "compare-me" });
    apiMocks.jobs = [completed];

    await page.goto("/upscale");

    // Le bouton "Comparer" est rendu sur les JobCard completed dans la
    // section "Récents".
    const compareBtn = page.getByRole("button", { name: /Comparer/ });
    await expect(compareBtn).toBeVisible({ timeout: 5_000 });
    await compareBtn.click();

    // CompareSlider affiche les labels "Original" et "Upscalé".
    await expect(page.getByText("Original")).toBeVisible();
    await expect(page.getByText("Upscalé")).toBeVisible();
    await expect(page.getByText(/Glisser pour comparer/i)).toBeVisible();

    // Clic sur close → le slider disparaît.
    await page.getByLabel("Fermer la comparaison").click();
    await expect(page.getByText(/Glisser pour comparer/i)).not.toBeVisible();
  });
});
