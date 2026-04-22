import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JobResponse } from "@/lib/api";
import * as api from "@/lib/api";
import { useJobStore } from "./useJobStore";

function makeJob(overrides: Partial<JobResponse> = {}): JobResponse {
  return {
    id: "job-1",
    user_id: "user-1",
    status: "pending",
    input_key: "uploads/abc.png",
    output_key: null,
    scale_factor: 4,
    model_name: "drct-l",
    input_width: 100,
    input_height: 100,
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

describe("useJobStore", () => {
  beforeEach(() => {
    // Réinitialise le state du store entre chaque test (singleton global).
    useJobStore.setState({ jobs: [], isLoading: false });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("fetchJobs", () => {
    it("should populate jobs from API", async () => {
      const jobs = [makeJob({ id: "j1" }), makeJob({ id: "j2" })];
      vi.spyOn(api, "listJobs").mockResolvedValue(jobs);

      const { result } = renderHook(() => useJobStore());

      await act(async () => {
        await result.current.fetchJobs();
      });

      expect(result.current.jobs).toHaveLength(2);
      expect(result.current.jobs[0]?.id).toBe("j1");
      expect(result.current.isLoading).toBe(false);
    });

    it("should set isLoading during the fetch", async () => {
      let resolve!: (v: JobResponse[]) => void;
      vi.spyOn(api, "listJobs").mockReturnValue(
        new Promise<JobResponse[]>((r) => {
          resolve = r;
        }),
      );

      const { result } = renderHook(() => useJobStore());
      let promise!: Promise<void>;

      act(() => {
        promise = result.current.fetchJobs();
      });

      expect(result.current.isLoading).toBe(true);

      await act(async () => {
        resolve([]);
        await promise;
      });

      expect(result.current.isLoading).toBe(false);
    });

    it("should reset isLoading on API error", async () => {
      vi.spyOn(api, "listJobs").mockRejectedValue(new Error("network"));

      const { result } = renderHook(() => useJobStore());

      await act(async () => {
        await result.current.fetchJobs();
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.jobs).toEqual([]);
    });
  });

  describe("submitJob", () => {
    it("should prepend the new job to the list", async () => {
      useJobStore.setState({ jobs: [makeJob({ id: "old" })] });

      const newJob = makeJob({ id: "new" });
      vi.spyOn(api, "createJob").mockResolvedValue(newJob);

      const { result } = renderHook(() => useJobStore());

      await act(async () => {
        await result.current.submitJob("uploads/abc.png", 4, "drct-l");
      });

      expect(result.current.jobs).toHaveLength(2);
      expect(result.current.jobs[0]?.id).toBe("new");
      expect(result.current.jobs[1]?.id).toBe("old");
    });
  });

  describe("updateJobProgress", () => {
    it("should update progress and status of a specific job", () => {
      useJobStore.setState({
        jobs: [makeJob({ id: "j1", progress: 0 }), makeJob({ id: "j2", progress: 0 })],
      });

      const { result } = renderHook(() => useJobStore());

      act(() => {
        result.current.updateJobProgress("j1", 0.5, "processing");
      });

      expect(result.current.jobs[0]?.progress).toBe(0.5);
      expect(result.current.jobs[0]?.status).toBe("processing");
      // j2 ne doit pas être touché.
      expect(result.current.jobs[1]?.progress).toBe(0);
    });

    it("should do nothing for unknown job id", () => {
      useJobStore.setState({ jobs: [makeJob({ id: "j1", progress: 0.3 })] });

      const { result } = renderHook(() => useJobStore());

      act(() => {
        result.current.updateJobProgress("unknown", 0.9, "processing");
      });

      expect(result.current.jobs[0]?.progress).toBe(0.3);
    });
  });

  describe("updateJobCompleted", () => {
    it("should mark the job as completed with the output key", () => {
      useJobStore.setState({ jobs: [makeJob({ id: "j1", progress: 0.5 })] });

      const { result } = renderHook(() => useJobStore());

      act(() => {
        result.current.updateJobCompleted("j1", "results/abc.png");
      });

      const updated = result.current.jobs[0];
      expect(updated?.status).toBe("completed");
      expect(updated?.progress).toBe(1);
      expect(updated?.output_key).toBe("results/abc.png");
    });
  });

  describe("updateJobFailed", () => {
    it("should mark the job as failed with error message", () => {
      useJobStore.setState({ jobs: [makeJob({ id: "j1" })] });

      const { result } = renderHook(() => useJobStore());

      act(() => {
        result.current.updateJobFailed("j1", "OOM");
      });

      expect(result.current.jobs[0]?.status).toBe("failed");
      expect(result.current.jobs[0]?.error_message).toBe("OOM");
    });
  });

  describe("removeJob", () => {
    it("should cancel the job via API and remove it from state", async () => {
      useJobStore.setState({
        jobs: [makeJob({ id: "j1" }), makeJob({ id: "j2" })],
      });

      vi.spyOn(api, "cancelJob").mockResolvedValue(undefined);

      const { result } = renderHook(() => useJobStore());

      await act(async () => {
        await result.current.removeJob("j1");
      });

      expect(result.current.jobs).toHaveLength(1);
      expect(result.current.jobs[0]?.id).toBe("j2");
      expect(api.cancelJob).toHaveBeenCalledWith("j1");
    });
  });
});
