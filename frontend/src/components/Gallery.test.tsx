import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { JobResponse } from "@/lib/api";
import { Gallery } from "./Gallery";

function makeJob(overrides: Partial<JobResponse> = {}): JobResponse {
  return {
    id: "job-1",
    user_id: "user-1",
    status: "completed",
    input_key: "uploads/abc.png",
    output_key: "results/abc.png",
    scale_factor: 4,
    model_name: "drct-l",
    input_width: 1920,
    input_height: 1080,
    output_width: 7680,
    output_height: 4320,
    gpu_backend: "local",
    progress: 1,
    error_message: null,
    prefer_local: null,
    created_at: "2026-04-09T00:00:00Z",
    updated_at: "2026-04-09T00:00:00Z",
    completed_at: "2026-04-09T00:00:05Z",
    ...overrides,
  };
}

describe("Gallery", () => {
  it("should render empty state when no jobs", () => {
    render(<Gallery jobs={[]} />);
    expect(screen.getByText("Aucun résultat à afficher")).toBeInTheDocument();
  });

  it("should render one image per job", () => {
    const jobs = [makeJob({ id: "j1" }), makeJob({ id: "j2" }), makeJob({ id: "j3" })];
    render(<Gallery jobs={jobs} />);

    const images = screen.getAllByRole("img");
    expect(images).toHaveLength(3);
    // URL inclut le token en query param pour authentifier les <img> natives.
    expect(images[0].getAttribute("src")).toMatch(/^\/api\/jobs\/j1\/download\?token=/);
    expect(images[1].getAttribute("src")).toMatch(/^\/api\/jobs\/j2\/download\?token=/);
  });

  it("should display output dimensions on each tile", () => {
    render(<Gallery jobs={[makeJob({ output_width: 4096, output_height: 2160 })]} />);
    expect(screen.getByText("4096×2160")).toBeInTheDocument();
  });

  it("should display model and scale factor metadata", () => {
    render(<Gallery jobs={[makeJob({ model_name: "hat-l", scale_factor: 2 })]} />);
    expect(screen.getByText(/hat-l/)).toBeInTheDocument();
    expect(screen.getByText(/2×/)).toBeInTheDocument();
  });

  it("should call onZoom when zoom button is clicked", async () => {
    const user = userEvent.setup();
    const onZoom = vi.fn();
    const job = makeJob({ id: "job-zoom" });

    render(<Gallery jobs={[job]} onZoom={onZoom} />);

    await user.click(screen.getByTitle("Inspecter"));
    expect(onZoom).toHaveBeenCalledWith(job);
  });

  it("should not render zoom button when onZoom is not provided", () => {
    render(<Gallery jobs={[makeJob()]} />);
    expect(screen.queryByTitle("Inspecter")).not.toBeInTheDocument();
  });

  it("should call onCompare when compare button is clicked", async () => {
    const user = userEvent.setup();
    const onCompare = vi.fn();
    const job = makeJob({ id: "job-compare" });

    render(<Gallery jobs={[job]} onCompare={onCompare} />);

    await user.click(screen.getByTitle("Comparer avant/après"));
    expect(onCompare).toHaveBeenCalledWith(job);
  });

  it("should not render compare button when onCompare is not provided", () => {
    render(<Gallery jobs={[makeJob()]} />);
    expect(screen.queryByTitle("Comparer avant/après")).not.toBeInTheDocument();
  });

  it("should always render the download button", () => {
    render(<Gallery jobs={[makeJob()]} />);
    expect(screen.getByTitle("Télécharger")).toBeInTheDocument();
  });

  it("should use lazy loading for images", () => {
    render(<Gallery jobs={[makeJob()]} />);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("loading", "lazy");
  });
});
