import { test, expect } from "./fixtures";

test.describe("Smoke — app mount + navigation", () => {
  test.beforeEach(async ({ page, apiMocks }) => {
    await apiMocks.install(page);
  });

  test("should render the sidebar with all 5 navigation items", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "GEGM" })).toBeVisible();
    // Sidebar — les 5 items sont tous visibles.
    await expect(page.getByRole("link", { name: /Upscaler/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Batch/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Galerie/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Historique/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Paramètres/ })).toBeVisible();
  });

  test("should redirect / to /upscale by default", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/upscale$/);
    await expect(page.getByRole("heading", { name: "Upscaler" })).toBeVisible();
  });

  test("should navigate between pages via sidebar links", async ({ page }) => {
    await page.goto("/upscale");

    await page.getByRole("link", { name: /Galerie/ }).click();
    await expect(page).toHaveURL(/\/gallery$/);
    await expect(page.getByRole("heading", { name: "Galerie" })).toBeVisible();

    await page.getByRole("link", { name: /Historique/ }).click();
    await expect(page).toHaveURL(/\/history$/);
    await expect(page.getByRole("heading", { name: "Historique" })).toBeVisible();

    await page.getByRole("link", { name: /Paramètres/ }).click();
    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByRole("heading", { name: "Paramètres" })).toBeVisible();
  });

  test("should navigate via Cmd+1..5 keyboard shortcuts", async ({ page }) => {
    await page.goto("/upscale");

    const mod = process.platform === "darwin" ? "Meta" : "Control";
    await page.keyboard.press(`${mod}+2`);
    await expect(page).toHaveURL(/\/batch$/);

    await page.keyboard.press(`${mod}+3`);
    await expect(page).toHaveURL(/\/gallery$/);

    await page.keyboard.press(`${mod}+5`);
    await expect(page).toHaveURL(/\/settings$/);

    await page.keyboard.press(`${mod}+1`);
    await expect(page).toHaveURL(/\/upscale$/);
  });

  test("should open the command palette with Cmd+K", async ({ page }) => {
    await page.goto("/upscale");
    // Le composant `CommandPalette` est lazy-loaded (React.lazy + Suspense
    // dans App.tsx) — sans attendre la fin du chunk load, le listener
    // Cmd+K n'est pas encore enregistré. `networkidle` garantit que tous
    // les chunks initiaux ont été fetched.
    await page.waitForLoadState("networkidle");
    const mod = process.platform === "darwin" ? "Meta" : "Control";
    // Playwright utilise `event.key` (valeur), pas `event.code` (touche
    // physique). Minuscule `k` → `event.key === "k"`, ce qui matche le
    // handler de CommandPalette.
    await page.keyboard.press(`${mod}+k`);
    await expect(
      page.getByPlaceholder("Rechercher une commande..."),
    ).toBeVisible();
  });
});
