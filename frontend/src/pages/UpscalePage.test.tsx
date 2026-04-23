import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import type { JobResponse } from "@/lib/api";
import { useJobStore } from "@/stores/useJobStore";
import { UpscalePage } from "./UpscalePage";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listJobs: vi.fn().mockResolvedValue([]),
    cancelJob: vi.fn(),
    createJob: vi.fn(),
    uploadImage: vi.fn(),
    getJob: vi.fn(),
  };
});

vi.mock("@/hooks/useSystemResources", () => ({
  useSystemResources: () => ({
    refresh: vi.fn().mockResolvedValue(null),
    verdict: null,
  }),
}));

vi.mock("@/hooks/useTauriDragDrop", () => ({
  useTauriDragDrop: () => undefined,
}));

// useSSE est lourd à mocker, on le remplace par un no-op qui accepte l'API.
vi.mock("@/hooks/useSSE", () => ({
  useSSE: () => undefined,
}));

function makeJob(overrides: Partial<JobResponse> = {}): JobResponse {
  return {
    id: "job-" + Math.random().toString(36).slice(2, 8),
    user_id: "u1",
    status: "completed",
    input_key: "uploads/a.png",
    output_key: "results/a.png",
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
    created_at: "2026-04-22T00:00:00Z",
    updated_at: "2026-04-22T00:01:00Z",
    completed_at: "2026-04-22T00:01:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
});

afterEach(() => {
  useJobStore.setState({ jobs: [], isLoading: false });
  vi.mocked(api.listJobs).mockResolvedValue([]);
});

describe("UpscalePage", () => {
  it("should render the hero title", () => {
    render(<UpscalePage />);
    expect(screen.getByRole("heading", { name: "Upscaler" })).toBeInTheDocument();
  });

  it("should render the DropZone and scale factor selectors", () => {
    render(<UpscalePage />);
    // "Glisser une image" apparaît à la fois dans le sous-titre du hero
    // et dans la DropZone — on accepte plusieurs matchs.
    expect(screen.getAllByText(/Glisser une image/i).length).toBeGreaterThan(0);
    // Les sélecteurs 2× et 4× sont toujours visibles.
    expect(screen.getByRole("button", { name: "2×" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "4×" })).toBeInTheDocument();
    // L'info du modèle courant est affichée à côté des facteurs.
    expect(screen.getByText(/Modèle/i)).toBeInTheDocument();
  });

  it("should display the derived model for the current scale factor", async () => {
    const user = userEvent.setup();
    render(<UpscalePage />);

    // Par défaut : ×4 → DRCT-L.
    expect(screen.getByText(/DRCT-L/i)).toBeInTheDocument();

    // Switch à ×2 → HAT-L.
    await user.click(screen.getByRole("button", { name: "2×" }));
    expect(screen.getByText(/HAT-L/i)).toBeInTheDocument();
  });

  it("should not show the Lancer button until a file is selected", () => {
    render(<UpscalePage />);
    expect(screen.queryByRole("button", { name: /Lancer l'upscale/i })).not.toBeInTheDocument();
  });

  it("should display completed jobs in the 'Récents' section", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      makeJob({ id: "c1" }),
      makeJob({ id: "c2" }),
    ]);
    render(<UpscalePage />);
    expect(await screen.findByText(/Récents/i)).toBeInTheDocument();
  });
});
