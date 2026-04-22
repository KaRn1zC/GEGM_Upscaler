import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import type { JobResponse } from "@/lib/api";
import { useJobStore } from "@/stores/useJobStore";
import { GalleryPage } from "./GalleryPage";

// Mock minimal de `@/lib/api` : seul `listJobs` est appelé par
// `useJobStore.fetchJobs` au montage. On le stub par défaut à `[]` et
// chaque test peut override via `vi.mocked(api.listJobs).mockResolvedValue(...)`.
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

// cmdk et zoom-pan-pinch appellent `scrollIntoView` (absent en jsdom) —
// on stub le minimum pour que le rendu passe sans casser.
beforeEach(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
});

afterEach(() => {
  // Reset le store Zustand entre chaque test pour isoler l'état.
  useJobStore.setState({ jobs: [], isLoading: false });
  vi.mocked(api.listJobs).mockResolvedValue([]);
});

describe("GalleryPage", () => {
  it("should render the title", () => {
    render(<GalleryPage />);
    expect(screen.getByRole("heading", { name: "Galerie" })).toBeInTheDocument();
  });

  it("should show empty state when no completed jobs", async () => {
    render(<GalleryPage />);
    // Le useEffect déclenche fetchJobs qui passe par isLoading=true avant
    // de retomber à isLoading=false avec jobs=[]. On attend la transition.
    expect(
      await screen.findByText(/Aucun résultat disponible/i),
    ).toBeInTheDocument();
  });

  it("should show the loading spinner while fetching", () => {
    // On rend la page juste après setState isLoading=true, sans laisser le
    // fetch asynchrone se résoudre — le spinner doit être visible.
    useJobStore.setState({ isLoading: true });
    render(<GalleryPage />);
    expect(screen.queryByText(/Aucun résultat disponible/i)).not.toBeInTheDocument();
  });

  it("should filter to only completed jobs for the gallery grid", async () => {
    // On injecte les jobs via le mock de listJobs — le useEffect du store
    // écrase sinon le setState direct avec la réponse API.
    vi.mocked(api.listJobs).mockResolvedValue([
      makeJob({ id: "c1", status: "completed" }),
      makeJob({ id: "p1", status: "processing" }),
      makeJob({ id: "f1", status: "failed" }),
      makeJob({ id: "c2", status: "completed" }),
    ]);
    render(<GalleryPage />);
    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.queryByText(/Aucun résultat/i)).not.toBeInTheDocument();
  });

  it("should open ZoomViewer when a gallery tile is zoomed", async () => {
    const user = userEvent.setup();
    vi.mocked(api.listJobs).mockResolvedValue([
      makeJob({ id: "z1", output_width: 4096, output_height: 2160 }),
    ]);
    render(<GalleryPage />);

    const zoomBtn = await screen.findByTitle("Inspecter");
    await act(async () => {
      await user.click(zoomBtn);
    });

    // Le ZoomViewer a ses propres boutons Zoom avant/Zoom arrière que
    // Gallery n'a pas — c'est le signal fiable que le viewer est ouvert.
    expect(await screen.findByTitle("Zoom avant")).toBeInTheDocument();
    expect(screen.getByTitle("Zoom arrière")).toBeInTheDocument();
    expect(screen.getByTitle("Réinitialiser")).toBeInTheDocument();
  });
});
