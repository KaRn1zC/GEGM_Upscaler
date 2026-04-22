import { useEffect, useRef } from "react";
import { useJobStore } from "@/stores/useJobStore";
import { isTauri } from "@/lib/tauri";

/**
 * Déclenche une notification macOS à chaque transition `processing → completed`
 * ou `processing → failed` sur un job.
 *
 * No-op hors contexte Tauri. En mode Tauri, demande la permission au premier
 * mount puis écoute les changements du store Zustand pour diffuser les notifs.
 *
 * À monter une seule fois au niveau racine (`App.tsx`) — monter plusieurs
 * instances déclencherait des notifs dupliquées.
 */
export function useJobNotifications(): void {
  // Snapshot du statut précédent par job_id, utilisé pour détecter les
  // transitions. On ne stocke pas toute la liste — seulement le couple
  // (id → status), suffisant pour diffuser au bon moment.
  const previousStatuses = useRef<Map<string, string>>(new Map());
  const permissionGranted = useRef<boolean>(false);

  // Demande de permission au montage, une seule fois.
  useEffect(() => {
    if (!isTauri()) return;

    let cancelled = false;
    void (async () => {
      const { isPermissionGranted, requestPermission } = await import(
        "@tauri-apps/plugin-notification"
      );
      let granted = await isPermissionGranted();
      if (!granted) {
        const decision = await requestPermission();
        granted = decision === "granted";
      }
      if (!cancelled) {
        permissionGranted.current = granted;
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  // Abonnement au store : on diff les statuts entre renders pour détecter
  // les transitions significatives. `subscribe` évite de re-render à chaque
  // mise à jour — on ne fait que déclencher une side-effect.
  useEffect(() => {
    if (!isTauri()) return;

    const unsub = useJobStore.subscribe((state) => {
      const current = state.jobs;
      const prev = previousStatuses.current;
      const next = new Map<string, string>();

      for (const job of current) {
        next.set(job.id, job.status);
        const previousStatus = prev.get(job.id);

        // Transitions intéressantes : on notifie quand un job sort de l'état
        // "processing" vers un état terminal (completed / failed).
        const wasProcessing =
          previousStatus === "processing" || previousStatus === "queued";
        const isTerminal = job.status === "completed" || job.status === "failed";

        if (wasProcessing && isTerminal && permissionGranted.current) {
          void notify(job.id, job.status);
        }
      }

      previousStatuses.current = next;
    });

    return () => {
      unsub();
    };
  }, []);
}

async function notify(jobId: string, status: string): Promise<void> {
  const { sendNotification } = await import("@tauri-apps/plugin-notification");
  const shortId = jobId.slice(0, 8);

  if (status === "completed") {
    sendNotification({
      title: "Upscale terminé",
      body: `Job ${shortId} prêt à être téléchargé.`,
    });
  } else {
    sendNotification({
      title: "Upscale échoué",
      body: `Job ${shortId} a rencontré une erreur.`,
    });
  }
}
