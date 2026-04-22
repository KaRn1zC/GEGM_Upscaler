import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import type { JobResponse } from "@/lib/api";
import { useJobStore } from "@/stores/useJobStore";
import { BatchPage } from "./BatchPage";

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

// `useSystemResources` fait un `invoke` Tauri qui plante en jsdom — on
// le stub pour que le hook renvoie un verdict inoffensif.
vi.mock("@/hooks/useSystemResources", () => ({
  useSystemResources: () => ({
    refresh: vi.fn().mockResolvedValue(null),
    verdict: null,
  }),
}));

// `useTauriDragDrop` est no-op hors Tauri mais on le stub explicitement
// pour éviter tout effet de bord pendant les tests.
vi.mock("@/hooks/useTauriDragDrop", () => ({
  useTauriDragDrop: () => undefined,
}));

function makeJob(overrides: Partial<JobResponse> = {}): JobResponse {
  return {
    id: "job-" + Math.random().toString(36).slice(2, 8),
    user_id: "u1",
    status: "processing",
    input_key: "uploads/a.png",
    output_key: null,
    scale_factor: 4,
    model_name: "drct-l",
    input_width: 1000,
    input_height: 800,
    output_width: null,
    output_height: null,
    gpu_backend: "cloud",
    progress: 0.5,
    error_message: null,
    prefer_local: null,
    created_at: "2026-04-22T00:00:00Z",
    updated_at: "2026-04-22T00:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

afterEach(() => {
  useJobStore.setState({ jobs: [], isLoading: false });
  vi.mocked(api.listJobs).mockResolvedValue([]);
});

describe("BatchPage", () => {
  it("should render the title", () => {
    render(<BatchPage />);
    expect(screen.getByRole("heading", { name: "Batch" })).toBeInTheDocument();
  });

  it("should render the BatchPanel drop zone", () => {
    render(<BatchPage />);
    // Le texte de la dropzone de BatchPanel est "Glisser plusieurs images".
    expect(screen.getByText(/Glisser plusieurs images/i)).toBeInTheDocument();
  });

  it("should show the active jobs counter when at least one job is in progress", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      makeJob({ id: "p1", status: "processing" }),
      makeJob({ id: "q1", status: "queued" }),
      makeJob({ id: "c1", status: "completed" }),
    ]);
    render(<BatchPage />);
    // "En cours (2)" — 2 jobs actifs parmi les 3 total.
    expect(await screen.findByText(/En cours \(2\)/i)).toBeInTheDocument();
    // Le compteur global affiche 1 terminé sur 3.
    expect(screen.getByText(/terminés/i)).toBeInTheDocument();
  });

  it("should not display the active section when nothing is in progress", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      makeJob({ id: "c1", status: "completed" }),
      makeJob({ id: "f1", status: "failed" }),
    ]);
    render(<BatchPage />);
    // On attend que fetchJobs ait terminé — présence des jobs sans
    // section "En cours".
    await screen.findByText(/terminés/i);
    expect(screen.queryByText(/En cours \(/i)).not.toBeInTheDocument();
  });
});
