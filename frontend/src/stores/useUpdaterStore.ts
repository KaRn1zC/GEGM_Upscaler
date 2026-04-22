import { create } from "zustand";
import { isTauri } from "@/lib/tauri";

export interface UpdateInfo {
  version: string;
  currentVersion: string;
  body?: string;
  date?: string;
}

export type UpdaterPhase =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "installing"
  | "error";

interface UpdaterState {
  phase: UpdaterPhase;
  update: UpdateInfo | null;
  progress: { downloaded: number; total: number };
  error: string | null;
  checkedOnce: boolean;

  checkNow: () => Promise<void>;
  installAndRestart: () => Promise<void>;
  dismiss: () => void;
}

/**
 * Store Zustand pour l'état du updater Tauri — partagé entre la bannière
 * globale (`App.tsx`) et le bouton manuel de `SettingsPage` pour qu'ils
 * restent synchronisés (un check manuel fait aussi apparaître la bannière).
 *
 * La signature des bundles utilise une clé Tauri-native (cf. `tauri.conf.json`
 * champ `plugins.updater.pubkey`) — indépendante de l'Apple Developer Program.
 */
export const useUpdaterStore = create<UpdaterState>((set) => ({
  phase: "idle",
  update: null,
  progress: { downloaded: 0, total: 0 },
  error: null,
  checkedOnce: false,

  checkNow: async () => {
    if (!isTauri()) return;
    set({ phase: "checking", error: null, checkedOnce: true });
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const result = await check();
      if (result) {
        set({
          update: {
            version: result.version,
            currentVersion: result.currentVersion,
            body: result.body,
            date: result.date,
          },
          phase: "available",
        });
      } else {
        set({ update: null, phase: "idle" });
      }
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : String(err),
        phase: "error",
      });
    }
  },

  installAndRestart: async () => {
    if (!isTauri()) return;
    set({ phase: "downloading", error: null, progress: { downloaded: 0, total: 0 } });
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const { relaunch } = await import("@tauri-apps/plugin-process");
      const result = await check();
      if (!result) {
        set({ phase: "idle" });
        return;
      }
      await result.downloadAndInstall((event) => {
        if (event.event === "Started") {
          set({ progress: { downloaded: 0, total: event.data.contentLength ?? 0 } });
        } else if (event.event === "Progress") {
          set((s) => ({
            progress: {
              downloaded: s.progress.downloaded + event.data.chunkLength,
              total: s.progress.total,
            },
          }));
        } else if (event.event === "Finished") {
          set({ phase: "installing" });
        }
      });
      // L'app va se relancer — on ne verra pas ce qui suit.
      await relaunch();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : String(err),
        phase: "error",
      });
    }
  },

  dismiss: () => {
    set({ phase: "idle", update: null });
  },
}));
