import { test, expect, makeJob } from "./fixtures";

test.describe("Galerie — affichage + ZoomViewer", () => {
  test.beforeEach(async ({ page, apiMocks }) => {
    await apiMocks.install(page);
  });

  test("should show empty state when no completed jobs", async ({ page, apiMocks }) => {
    apiMocks.jobs = [];
    await page.goto("/gallery");
    await expect(page.getByText(/Aucun résultat disponible/i)).toBeVisible();
  });

  test("should display completed jobs in the grid", async ({ page, apiMocks }) => {
    apiMocks.jobs = [
      makeJob({ id: "c1", output_width: 4000, output_height: 3200 }),
      makeJob({ id: "c2", output_width: 8192, output_height: 4320 }),
      makeJob({ id: "c3", output_width: 2560, output_height: 1440 }),
    ];
    await page.goto("/gallery");
    // Le compteur dans le header doit afficher 3.
    await expect(page.getByText("3", { exact: true }).first()).toBeVisible();
    // Aucun empty state.
    await expect(page.getByText(/Aucun résultat/i)).not.toBeVisible();
  });

  test("should filter out non-completed jobs from the grid", async ({ page, apiMocks }) => {
    apiMocks.jobs = [
      makeJob({ id: "c1", status: "completed" }),
      makeJob({ id: "p1", status: "processing" }),
      makeJob({ id: "f1", status: "failed" }),
    ];
    await page.goto("/gallery");
    // Seul 1 completed → compteur à 1.
    await expect(page.getByText("1", { exact: true }).first()).toBeVisible();
  });

  test("should open ZoomViewer on Inspecter click and show dimensions", async ({
    page,
    apiMocks,
  }) => {
    apiMocks.jobs = [
      makeJob({ id: "zoom-me", output_width: 4096, output_height: 2160 }),
    ];
    await page.goto("/gallery");

    // Le bouton "Inspecter" est dans un overlay masqué par `opacity-0`
    // révélé par `group-hover:opacity-100`. `force: true` bypass la
    // vérification de visibilité Playwright (l'élément est dans le DOM,
    // juste pas "visible" au sens CSS — c'est suffisant pour simuler
    // l'intent utilisateur).
    await page.getByTitle("Inspecter").first().click({ force: true });

    // Le ZoomViewer a des boutons zoom uniques pas présents dans Gallery.
    await expect(page.getByTitle("Zoom avant")).toBeVisible();
    await expect(page.getByTitle("Zoom arrière")).toBeVisible();
    await expect(page.getByTitle("Réinitialiser")).toBeVisible();

    // Le texte "4096×2160" apparaît 2× (une fois dans la tile Gallery en
    // fond, une fois dans le label flottant du ZoomViewer) — on vérifie
    // juste qu'au moins un est visible (ce qui confirme l'ouverture).
    await expect(page.getByText(/4096×2160/).first()).toBeVisible();
  });

  test("should close ZoomViewer via the X button", async ({ page, apiMocks }) => {
    apiMocks.jobs = [makeJob({ id: "zoom-close" })];
    await page.goto("/gallery");

    await page.getByTitle("Inspecter").first().click({ force: true });
    await expect(page.getByTitle("Zoom avant")).toBeVisible();

    await page.getByLabel("Fermer le viewer").click();
    await expect(page.getByTitle("Zoom avant")).not.toBeVisible();
  });
});
