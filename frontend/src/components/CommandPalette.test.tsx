import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandPalette } from "./CommandPalette";

// Mock de react-router-dom pour pouvoir asserter les appels à navigate
// sans avoir besoin d'un BrowserRouter dans le test.
const navigateMock = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigateMock,
}));

function pressMetaK() {
  const event = new KeyboardEvent("keydown", {
    key: "k",
    metaKey: true,
    bubbles: true,
    cancelable: true,
  });
  document.dispatchEvent(event);
}

// cmdk appelle `scrollIntoView` à l'ouverture pour amener l'item actif
// dans le viewport, mais jsdom ne l'implémente pas. On le stub en no-op
// pour la durée du fichier — pas d'impact sur la logique testée.
beforeEach(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
});

describe("CommandPalette", () => {
  beforeEach(() => {
    navigateMock.mockClear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("should not render the dialog content when closed", () => {
    render(<CommandPalette />);
    // L'input n'est pas dans le DOM tant que le dialog n'est pas ouvert.
    expect(
      screen.queryByPlaceholderText("Rechercher une commande..."),
    ).not.toBeInTheDocument();
  });

  it("should open the dialog when Cmd+K is pressed", () => {
    render(<CommandPalette />);
    act(() => {
      pressMetaK();
    });
    expect(screen.getByPlaceholderText("Rechercher une commande...")).toBeInTheDocument();
  });

  it("should toggle closed on a second Cmd+K", () => {
    render(<CommandPalette />);
    act(() => {
      pressMetaK();
    });
    expect(screen.getByPlaceholderText("Rechercher une commande...")).toBeInTheDocument();
    act(() => {
      pressMetaK();
    });
    // Radix anime la fermeture ; on avance les timers et on vérifie que
    // l'input a quitté le DOM (ou est masqué via `data-state=closed`).
    act(() => {
      vi.advanceTimersByTime(500);
    });
    const input = screen.queryByPlaceholderText("Rechercher une commande...");
    // Certaines primitives radix retirent le noeud, d'autres le masquent —
    // on accepte les deux comme "fermé".
    expect(
      input === null ||
        input.closest("[data-state='closed']") !== null ||
        !input.isConnected,
    ).toBe(true);
  });

  it("should display the 5 navigation entries when open", () => {
    render(<CommandPalette />);
    act(() => {
      pressMetaK();
    });
    expect(screen.getByText("Upscaler")).toBeInTheDocument();
    expect(screen.getByText("Batch")).toBeInTheDocument();
    expect(screen.getByText("Galerie")).toBeInTheDocument();
    expect(screen.getByText("Historique")).toBeInTheDocument();
    expect(screen.getByText("Paramètres")).toBeInTheDocument();
  });

  it("should display the quick action entries when open", () => {
    render(<CommandPalette />);
    act(() => {
      pressMetaK();
    });
    expect(screen.getByText("Nouvel upscale")).toBeInTheDocument();
    expect(screen.getByText("Nouveau batch")).toBeInTheDocument();
  });

  it("should navigate to /gallery when Galerie is selected", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CommandPalette />);
    act(() => {
      pressMetaK();
    });
    await user.click(screen.getByText("Galerie"));
    // Le runCommand diffère le navigate via setTimeout(80) pour laisser
    // le dialog animer sa fermeture — on avance les timers.
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(navigateMock).toHaveBeenCalledWith("/gallery");
  });

  it("should navigate to /upscale when Nouvel upscale is selected", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CommandPalette />);
    act(() => {
      pressMetaK();
    });
    await user.click(screen.getByText("Nouvel upscale"));
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(navigateMock).toHaveBeenCalledWith("/upscale");
  });
});
