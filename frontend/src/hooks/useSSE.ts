import { useEffect, useRef } from "react";
import { getJob, getProgressStreamUrl } from "@/lib/api";

export interface SSEProgressEvent {
  job_id: string;
  status: string;
  progress: number;
  step?: string;
  output_key?: string;
  error_message?: string;
}

interface UseSSEOptions {
  jobId: string | null;
  onProgress: (data: SSEProgressEvent) => void;
  onComplete: (data: SSEProgressEvent) => void;
  onError: (data: SSEProgressEvent) => void;
}

// Au-delà de ce délai sans event SSE, on requête l'état du job via l'API
// REST en filet de secours. Couvre le cas où le stream s'est tu sans
// fermeture explicite (proxy qui coupe silencieusement, process backend
// qui crash entre deux publish Redis, etc.).
const STALE_STREAM_MS = 45_000;
// Fréquence du timer de check : suffisamment fréquente pour réagir vite,
// pas trop agressive pour éviter de spammer l'API.
const FALLBACK_CHECK_INTERVAL_MS = 15_000;

/**
 * Abonne l'UI au stream SSE de progression d'un job.
 *
 * L'`EventSource` natif gère la reconnexion automatique sur erreur réseau
 * tant que `close()` n'est pas appelé. La version précédente appelait
 * `close()` dans le handler `error` global ce qui tuait le retry et
 * laissait l'UI bloquée sur le dernier event reçu — typiquement "40 %
 * en cours" alors que le job était déjà `completed` en DB.
 *
 * Le correctif distingue :
 *   - **Erreur applicative** (backend émet un `event: error` avec payload
 *     JSON) → l'event est un `MessageEvent`, on propage via `onError`
 *     et on ferme proprement.
 *   - **Erreur réseau** (connexion coupée, pas de `MessageEvent`) → on
 *     laisse l'`EventSource` reconnecter silencieusement.
 *
 * Filet de secours : un timer vérifie toutes les `FALLBACK_CHECK_INTERVAL_MS`
 * secondes si plus aucun event n'a été reçu depuis `STALE_STREAM_MS`. Si
 * oui, il requête l'état réel du job via `GET /api/jobs/:id` et déclenche
 * le bon callback terminal si le job s'est terminé entretemps. Ça couvre
 * les pires cas (proxy qui mange le stream sans le refermer côté client).
 */
export function useSSE({ jobId, onProgress, onComplete, onError }: UseSSEOptions) {
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const es = new EventSource(getProgressStreamUrl(jobId));
    sourceRef.current = es;

    let lastEventAt = Date.now();
    let terminated = false;

    const markEvent = () => {
      lastEventAt = Date.now();
    };

    const closeAll = () => {
      terminated = true;
      es.close();
    };

    es.addEventListener("progress", (e) => {
      markEvent();
      const data = JSON.parse(e.data) as SSEProgressEvent;
      onProgress(data);
    });

    es.addEventListener("completed", (e) => {
      markEvent();
      const data = JSON.parse(e.data) as SSEProgressEvent;
      onComplete(data);
      closeAll();
    });

    es.addEventListener("error", (e) => {
      // Distinction réseau vs applicatif : seul le second a un payload JSON.
      if (e instanceof MessageEvent && typeof e.data === "string") {
        markEvent();
        const data = JSON.parse(e.data) as SSEProgressEvent;
        onError(data);
        closeAll();
        return;
      }
      // Erreur réseau : EventSource reconnectera tout seul tant que la
      // connexion n'est pas explicitement closed. Ne rien faire ici.
    });

    // Filet de secours : si le stream est silencieux trop longtemps, on
    // requête l'état réel en DB et on propage la transition finale si le
    // job est déjà terminé côté backend.
    const fallbackTimer = window.setInterval(async () => {
      if (terminated) return;
      const silentMs = Date.now() - lastEventAt;
      if (silentMs < STALE_STREAM_MS) return;

      try {
        const job = await getJob(jobId);
        const payload: SSEProgressEvent = {
          job_id: job.id,
          status: job.status,
          progress: job.progress ?? 0,
          output_key: job.output_key ?? undefined,
          error_message: job.error_message ?? undefined,
        };
        if (job.status === "completed") {
          onComplete(payload);
          closeAll();
        } else if (job.status === "failed" || job.status === "cancelled") {
          onError(payload);
          closeAll();
        } else {
          // Pas encore terminal — on publie l'état courant au moins pour
          // que l'UI sorte d'un affichage figé.
          onProgress(payload);
          lastEventAt = Date.now();
        }
      } catch (err) {
        // L'API peut être temporairement indispo ; on réessaiera au prochain tick.
        console.warn(`[useSSE] fallback fetch échoué pour ${jobId}:`, err);
      }
    }, FALLBACK_CHECK_INTERVAL_MS);

    return () => {
      window.clearInterval(fallbackTimer);
      es.close();
      sourceRef.current = null;
    };
  }, [jobId, onProgress, onComplete, onError]);
}
