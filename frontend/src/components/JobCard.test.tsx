import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { JobResponse } from "@/lib/api";
import { JobCard } from "./JobCard";

function makeJob(overrides: Partial<JobResponse> = {}): JobResponse {
  return {
    id: "job-1",
    user_id: "user-1",
    status: "pending",
    input_key: "uploads/abc.png",
    output_key: null,
    scale_factor: 4,
    model_name: "drct-l",
    input_width: 1920,
    input_height: 1080,
    output_width: null,
    output_height: null,
    gpu_backend: null,
    progress: 0,
    error_message: null,
    prefer_local: null,
    created_at: "2026-04-09T00:00:00Z",
    updated_at: "2026-04-09T00:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

describe("JobCard", () => {
  describe("status rendering", () => {
    it("should render pending status label", () => {
      render(<JobCard job={makeJob({ status: "pending" })} />);
      expect(screen.getByText("En attente")).toBeInTheDocument();
    });

    it("should render processing status with progress bar", () => {
      render(<JobCard job={makeJob({ status: "processing", progress: 0.5 })} />);
      expect(screen.getByText("En cours")).toBeInTheDocument();
      expect(screen.getByText("50%")).toBeInTheDocument();
    });

    it("should render completed status with 100%", () => {
      render(
        <JobCard
          job={makeJob({
            status: "completed",
            progress: 1,
            output_width: 7680,
            output_height: 4320,
          })}
        />,
      );
      expect(screen.getByText("Terminé")).toBeInTheDocument();
      expect(screen.getByText("100%")).toBeInTheDocument();
    });

    it("should render failed status with error message", () => {
      render(
        <JobCard job={makeJob({ status: "failed", error_message: "GPU OOM" })} />,
      );
      expect(screen.getByText("Échoué")).toBeInTheDocument();
      expect(screen.getByText("GPU OOM")).toBeInTheDocument();
    });

    it("should render cancelled status", () => {
      render(<JobCard job={makeJob({ status: "cancelled" })} />);
      expect(screen.getByText("Annulé")).toBeInTheDocument();
    });
  });

  describe("metadata display", () => {
    it("should show input dimensions and scale factor", () => {
      render(<JobCard job={makeJob({ input_width: 1920, input_height: 1080 })} />);
      expect(screen.getByText(/1920×1080/)).toBeInTheDocument();
      expect(screen.getByText(/4×/)).toBeInTheDocument();
    });

    it("should show output dimensions when completed", () => {
      render(
        <JobCard
          job={makeJob({
            status: "completed",
            output_width: 7680,
            output_height: 4320,
          })}
        />,
      );
      expect(screen.getByText(/7680×4320/)).toBeInTheDocument();
    });

    it("should display the model name badge", () => {
      render(<JobCard job={makeJob({ model_name: "hat-l" })} />);
      expect(screen.getByText("hat-l")).toBeInTheDocument();
    });

    it("should display the GPU backend badge when set", () => {
      render(<JobCard job={makeJob({ gpu_backend: "local" })} />);
      expect(screen.getByText("local")).toBeInTheDocument();
    });

    it("should not render GPU backend badge when null", () => {
      render(<JobCard job={makeJob({ gpu_backend: null })} />);
      expect(screen.queryByText("local")).not.toBeInTheDocument();
      expect(screen.queryByText("cloud")).not.toBeInTheDocument();
    });
  });

  describe("actions", () => {
    it("should call onCompare when comparer button is clicked", async () => {
      const user = userEvent.setup();
      const onCompare = vi.fn();
      const job = makeJob({ status: "completed", progress: 1 });

      render(<JobCard job={job} onCompare={onCompare} />);

      await user.click(screen.getByText("Comparer"));
      expect(onCompare).toHaveBeenCalledWith(job);
    });

    it("should call onDownload when download button is clicked", async () => {
      const user = userEvent.setup();
      const onDownload = vi.fn();
      const job = makeJob({ status: "completed", progress: 1 });

      render(<JobCard job={job} onDownload={onDownload} />);

      await user.click(screen.getByText("Télécharger"));
      expect(onDownload).toHaveBeenCalledWith(job);
    });

    it("should call onCancel when cancel button is clicked on active job", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      const job = makeJob({ status: "processing", progress: 0.5 });

      render(<JobCard job={job} onCancel={onCancel} />);

      await user.click(screen.getByText("Annuler"));
      expect(onCancel).toHaveBeenCalledWith(job);
    });

    it("should not render action buttons when handlers are not provided", () => {
      render(<JobCard job={makeJob({ status: "completed", progress: 1 })} />);
      expect(screen.queryByText("Comparer")).not.toBeInTheDocument();
      expect(screen.queryByText("Télécharger")).not.toBeInTheDocument();
    });

    it("should not render cancel button on completed jobs", () => {
      const onCancel = vi.fn();
      render(<JobCard job={makeJob({ status: "completed", progress: 1 })} onCancel={onCancel} />);
      expect(screen.queryByText("Annuler")).not.toBeInTheDocument();
    });
  });

  describe("progress bar", () => {
    it("should not render progress bar on pending jobs", () => {
      render(<JobCard job={makeJob({ status: "pending", progress: 0 })} />);
      expect(screen.queryByText("0%")).not.toBeInTheDocument();
    });

    it("should render progress bar on queued jobs", () => {
      render(<JobCard job={makeJob({ status: "queued", progress: 0.1 })} />);
      expect(screen.getByText("10%")).toBeInTheDocument();
    });

    it("should round the percentage", () => {
      render(<JobCard job={makeJob({ status: "processing", progress: 0.337 })} />);
      expect(screen.getByText("34%")).toBeInTheDocument();
    });
  });
});
