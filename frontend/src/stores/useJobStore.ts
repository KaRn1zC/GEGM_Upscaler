import { create } from "zustand";
import type { JobResponse } from "@/lib/api";
import {
  bulkDeleteJobs,
  cancelJob,
  createJob,
  deleteJob,
  listJobs,
  uploadImage,
} from "@/lib/api";
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
  cancelJob: (jobId: string) => Promise<void>;
  removeJob: (jobId: string) => Promise<void>;
  removeJobs: (jobIds: string[]) => Promise<number>;
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
    // Uploads en parallèle BORNÉ : un shooting de 200 photos ne doit pas
    // ouvrir 200 connexions simultanées (saturation bande passante +
    // rafale sur l'API). Les erreurs restent capturées individuellement
    // pour que l'échec d'un fichier ne bloque pas les autres.
    const CONCURRENT_UPLOADS = 4;
    const newJobs: JobResponse[] = [];
    const results: BatchItemResult[] = new Array<BatchItemResult>(files.length);

    const processOne = async (file: File): Promise<BatchItemResult> => {
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
    };

    // Pool maison : N workers piochent dans la liste — l'incrément est
    // sûr en JS mono-thread, inutile d'ajouter une dépendance type p-limit.
    let next = 0;
    const workers = Array.from(
      { length: Math.min(CONCURRENT_UPLOADS, files.length) },
      async () => {
        while (next < files.length) {
          const index = next++;
          results[index] = await processOne(files[index]);
        }
      },
    );
    await Promise.all(workers);

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

  cancelJob: async (jobId) => {
    try {
      await cancelJob(jobId);
      // Le job reste listé, passe en `cancelled` (il devient supprimable).
      set((s) => ({
        jobs: s.jobs.map((j) =>
          j.id === jobId ? { ...j, status: "cancelled" } : j,
        ),
      }));
    } catch (err) {
      console.error(`[useJobStore] Échec annulation job ${jobId}:`, err);
      throw err;
    }
  },

  removeJob: async (jobId) => {
    try {
      // Suppression réelle : fichiers (input + output) + ligne DB.
      await deleteJob(jobId);
      set((s) => ({ jobs: s.jobs.filter((j) => j.id !== jobId) }));
    } catch (err) {
      console.error(`[useJobStore] Échec suppression job ${jobId}:`, err);
      throw err;
    }
  },

  removeJobs: async (jobIds) => {
    try {
      const deleted = await bulkDeleteJobs(jobIds);
      // Le backend ignore les actifs/inconnus ; on retire de la liste les
      // ids demandés qui sont effectivement supprimables (terminés). Comme
      // l'API ne renvoie que le compte, on filtre sur le statut terminal
      // localement pour rester cohérent avec ce que le backend a supprimé.
      const terminal = new Set(["completed", "failed", "cancelled"]);
      const requested = new Set(jobIds);
      set((s) => ({
        jobs: s.jobs.filter(
          (j) => !(requested.has(j.id) && terminal.has(j.status)),
        ),
      }));
      return deleted;
    } catch (err) {
      console.error(`[useJobStore] Échec suppression groupée:`, err);
      throw err;
    }
  },
}));
