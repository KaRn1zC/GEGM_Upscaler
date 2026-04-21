import { create } from "zustand";
import type { JobResponse } from "@/lib/api";
import { cancelJob, createJob, listJobs, uploadImage } from "@/lib/api";
import type { ScaleFactor } from "@/lib/constants";

export interface BatchItemResult {
  file: File;
  jobId: string | null;
  error: string | null;
}

interface JobStore {
  jobs: JobResponse[];
  isLoading: boolean;

  fetchJobs: () => Promise<void>;
  submitJob: (
    inputKey: string,
    scaleFactor: ScaleFactor,
    modelName?: string,
    preferLocal?: boolean | null,
  ) => Promise<JobResponse>;
  submitBatch: (
    files: File[],
    scaleFactor: ScaleFactor,
    modelName?: string,
    preferLocal?: boolean | null,
  ) => Promise<BatchItemResult[]>;
  updateJobProgress: (jobId: string, progress: number, status: string) => void;
  updateJobCompleted: (jobId: string, outputKey: string) => void;
  updateJobFailed: (jobId: string, error: string) => void;
  removeJob: (jobId: string) => Promise<void>;
}

export const useJobStore = create<JobStore>((set) => ({
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

  submitJob: async (inputKey, scaleFactor, modelName, preferLocal) => {
    const job = await createJob({
      input_key: inputKey,
      scale_factor: scaleFactor,
      model_name: modelName,
      prefer_local: preferLocal,
    });
    set((s) => ({ jobs: [job, ...s.jobs] }));
    return job;
  },

  submitBatch: async (files, scaleFactor, modelName, preferLocal) => {
    // Upload + création de job en parallèle pour chaque fichier.
    // On capture les erreurs individuellement pour que l'échec d'un
    // fichier ne bloque pas les autres.
    const newJobs: JobResponse[] = [];
    const results = await Promise.all(
      files.map(async (file): Promise<BatchItemResult> => {
        try {
          const uploaded = await uploadImage(file);
          const job = await createJob({
            input_key: uploaded.key,
            scale_factor: scaleFactor,
            model_name: modelName,
            prefer_local: preferLocal,
          });
          newJobs.push(job);
          return { file, jobId: job.id, error: null };
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          return { file, jobId: null, error: msg };
        }
      }),
    );

    set((s) => ({ jobs: [...newJobs, ...s.jobs] }));

    return results;
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
        j.id === jobId ? { ...j, status: "failed", error_message: error } : j,
      ),
    }));
  },

  removeJob: async (jobId) => {
    await cancelJob(jobId);
    set((s) => ({ jobs: s.jobs.filter((j) => j.id !== jobId) }));
  },
}));
