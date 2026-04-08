import { useEffect, useRef } from "react";

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

export function useSSE({ jobId, onProgress, onComplete, onError }: UseSSEOptions) {
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const es = new EventSource(`/api/jobs/${jobId}/progress`);
    sourceRef.current = es;

    es.addEventListener("progress", (e) => {
      const data = JSON.parse(e.data) as SSEProgressEvent;
      onProgress(data);
    });

    es.addEventListener("completed", (e) => {
      const data = JSON.parse(e.data) as SSEProgressEvent;
      onComplete(data);
      es.close();
    });

    es.addEventListener("error", (e) => {
      if (e instanceof MessageEvent) {
        const data = JSON.parse(e.data) as SSEProgressEvent;
        onError(data);
      }
      es.close();
    });

    return () => {
      es.close();
      sourceRef.current = null;
    };
  }, [jobId, onProgress, onComplete, onError]);
}
