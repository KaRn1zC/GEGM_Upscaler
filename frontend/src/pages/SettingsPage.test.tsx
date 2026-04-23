import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { SettingsPage } from "./SettingsPage";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getCurrentUser: vi.fn(),
    getReadiness: vi.fn(),
  };
});

// usePreferences écrit dans localStorage — on le reset pour isoler les tests.
beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(api.getCurrentUser).mockResolvedValue({
    id: "user-1",
    email: "test@example.com",
    name: "Test User",
    created_at: "2026-01-01T00:00:00Z",
  });
  vi.mocked(api.getReadiness).mockResolvedValue({
    status: "ready",
    checks: { db: "ok", redis: "ok" },
  });
});

afterEach(() => {
  window.localStorage.clear();
});

describe("SettingsPage", () => {
  it("should render the title and main sections", () => {
    render(<SettingsPage />);
    expect(screen.getByRole("heading", { name: "Paramètres" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Compte" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Préférences" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "État du système" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "À propos" })).toBeInTheDocument();
  });

  it("should display the authenticated user after fetch", async () => {
    render(<SettingsPage />);
    expect(await screen.findByText("test@example.com")).toBeInTheDocument();
    expect(screen.getByText("Test User")).toBeInTheDocument();
  });

  it("should display an error when the user endpoint fails", async () => {
    vi.mocked(api.getCurrentUser).mockRejectedValue(new Error("401 Unauthorized"));
    render(<SettingsPage />);
    expect(
      await screen.findByText(/Impossible de récupérer l'utilisateur/i),
    ).toBeInTheDocument();
  });

  it("should display the health check statuses", async () => {
    render(<SettingsPage />);
    expect(await screen.findByText("Statut global")).toBeInTheDocument();
    expect(screen.getByText("Db")).toBeInTheDocument();
    expect(screen.getByText("Redis")).toBeInTheDocument();
  });

  it("should highlight the current default scale factor", () => {
    render(<SettingsPage />);
    // Par défaut, 4× est sélectionné (cf. usePreferences).
    const btn4 = screen.getByRole("button", { name: /4×/ });
    expect(btn4.className).toContain("bg-primary");
  });

  it("should display the scale→model mapping (info only)", () => {
    render(<SettingsPage />);
    // Nouveau comportement : le modèle n'est plus un choix mais une info
    // dérivée du scale_factor. La section "Modèles utilisés" liste
    // explicitement le mapping ×2 → HAT-L et ×4 → DRCT-L.
    expect(screen.getByText(/Modèles utilisés/i)).toBeInTheDocument();
    expect(screen.getAllByText(/HAT-L/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/DRCT-L/i).length).toBeGreaterThan(0);
  });

  it("should render the About section with static infos", () => {
    render(<SettingsPage />);
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
  });
});
