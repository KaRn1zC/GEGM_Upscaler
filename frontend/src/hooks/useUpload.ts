import { useCallback, useState } from "react";
import { API_BASE } from "@/lib/constants";
import { useAuthStore } from "@/stores/useAuthStore";

interface UploadState {
  isUploading: boolean;
  progress: number;
  error: string | null;
}

interface UploadResult {
  key: string;
  filename: string;
  size: number;
  content_type: string;
}

export function useUpload() {
  const [state, setState] = useState<UploadState>({
    isUploading: false,
    progress: 0,
    error: null,
  });

  const upload = useCallback(async (file: File): Promise<UploadResult> => {
    // Récupère (et refresh si nécessaire) le token AVANT de marquer
    // `isUploading: true`. En faisant le setState APRÈS le await,
    // le flag devient observable par les consommateurs (tests, UI)
    // seulement une fois que le XHR sera immédiatement créé et en vol
    // dans le même tick synchrone — pas d'état transitoire trompeur.
    const token = (await useAuthStore.getState().getValidToken()) ?? "";

    setState({ isUploading: true, progress: 0, error: null });

    return new Promise<UploadResult>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      form.append("file", file);

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100);
          setState((s) => ({ ...s, progress: pct }));
        }
      });

      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const result = JSON.parse(xhr.responseText) as UploadResult;
          setState({ isUploading: false, progress: 100, error: null });
          resolve(result);
        } else {
          const msg = `Upload échoué (HTTP ${xhr.status})`;
          setState({ isUploading: false, progress: 0, error: msg });
          reject(new Error(msg));
        }
      });

      xhr.addEventListener("error", () => {
        const msg = "Erreur réseau pendant l'upload";
        setState({ isUploading: false, progress: 0, error: msg });
        reject(new Error(msg));
      });

      xhr.open("POST", `${API_BASE}/uploads`);
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.send(form);
    });
  }, []);

  const reset = useCallback(() => {
    setState({ isUploading: false, progress: 0, error: null });
  }, []);

  return { ...state, upload, reset };
}
