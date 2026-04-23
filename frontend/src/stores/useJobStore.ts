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
  // Le backend dérive `model_name` de `scale_factor` (cf. SCALE_TO_MODEL).
  // Le client n'a plus à le fournir — simplification côté UI + garantie
  // anti-incohérence (un seul endroit qui tranche le couple model/scale).
  submitJob: (
    inputKey: string,
    scaleFactor: ScaleFactor,
    preferLocal?: boolean | null,
  ) => Promise<JobResponse>;
  submitBatch: (
    files: File[],
    scaleFactor: ScaleFactor,
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

  submitJob: async (inputKey, scaleFactor, preferLocal) => {
    const job = await createJob({
      input_key: inputKey,
      scale_factor: scaleFactor,
      prefer_local: preferLocal,
    });
    set((s) => ({ jobs: [job, ...s.jobs] }));
    return job;
  },

  submitBatch: async (files, scaleFactor, preferLocal) => {
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
    try {
      await cancelJob(jobId);
      set((s) => ({ jobs: s.jobs.filter((j) => j.id !== jobId) }));
    } catch (err) {
      // On log l'erreur plutôt que de la swaller silencieusement : si le
      // backend refuse l'annulation (409 sur un job déjà terminé), l'UI
      // affichait un clic sans effet, inexplicable côté utilisateur.
      console.error(`[useJobStore] Échec annulation job ${jobId}:`, err);
      throw err;
    }
  },
}));
