import { create } from "zustand";
import type { JobResponse } from "@/lib/api";
import { cancelJob, createJob, listJobs } from "@/lib/api";
import type { ScaleFactor } from "@/lib/constants";

interface JobStore {
  jobs: JobResponse[];
  isLoading: boolean;

  fetchJobs: () => Promise<void>;
  submitJob: (inputKey: string, scaleFactor: ScaleFactor, modelName?: string) => Promise<JobResponse>;
  updateJobProgress: (jobId: string, progress: number, status: string) => void;
  updateJobCompleted: (jobId: string, outputKey: string) => void;
  updateJobFailed: (jobId: string, error: string) => void;
  removeJob: (jobId: string) => Promise<void>;
}

export const useJobStore = create<JobStore>((set, get) => ({
  jobs: [],
  isLoading: false,

  fetchJobs: async () => {
    set({ isLoading: true });
    try {
      const jobs = await listJobs();
      set({ jobs, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  submitJob: async (inputKey, scaleFactor, modelName) => {
    const job = await createJob({
      input_key: inputKey,
      scale_factor: scaleFactor,
      model_name: modelName,
    });
    set((s) => ({ jobs: [job, ...s.jobs] }));
    return job;
  },

  updateJobProgress: (jobId, progress, status) => {
    set((s) => ({
      jobs: s.jobs.map((j) =>
        j.id === jobId ? { ...j, progress, status } : j,
      ),
    }));
  },

  updateJobCompleted: (jobId, outputKey) => {
    set((s) => ({
      jobs: s.jobs.map((j) =>
        j.id === jobId
          ? { ...j, status: "completed", progress: 1, output_key: outputKey }
          : j,
      ),
    }));
  },

  updateJobFailed: (jobId, error) => {
    set((s) => ({
      jobs: s.jobs.map((j) =>
        j.id === jobId
          ? { ...j, status: "failed", error_message: error }
          : j,
      ),
    }));
  },

  removeJob: async (jobId) => {
    await cancelJob(jobId);
    set((s) => ({ jobs: s.jobs.filter((j) => j.id !== jobId) }));
  },
}));
