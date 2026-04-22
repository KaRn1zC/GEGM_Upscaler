import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import type { JobResponse } from "@/lib/api";
import { useJobStore } from "@/stores/useJobStore";
import { HistoryPage } from "./HistoryPage";

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

afterEach(() => {
  useJobStore.setState({ jobs: [], isLoading: false });
  vi.mocked(api.listJobs).mockResolvedValue([]);
});

describe("HistoryPage", () => {
  it("should render the title", () => {
    render(<HistoryPage />);
    expect(screen.getByRole("heading", { name: "Historique" })).toBeInTheDocument();
  });

  it("should show empty state when no jobs", async () => {
    render(<HistoryPage />);
    expect(await screen.findByText(/Aucun job pour le moment/i)).toBeInTheDocument();
  });

  it("should display all jobs regardless of status (unlike Gallery)", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      makeJob({ id: "c1", status: "completed" }),
      makeJob({ id: "f1", status: "failed" }),
      makeJob({ id: "x1", status: "cancelled" }),
    ]);
    render(<HistoryPage />);
    // 3 jobs dans le compteur du header.
    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(screen.queryByText(/Aucun job/i)).not.toBeInTheDocument();
  });

  it("should show loading spinner while fetching", () => {
    useJobStore.setState({ isLoading: true });
    render(<HistoryPage />);
    expect(screen.queryByText(/Aucun job pour le moment/i)).not.toBeInTheDocument();
  });
});
