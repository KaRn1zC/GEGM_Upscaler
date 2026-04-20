import { API_BASE } from "./constants";

// ── Types ────────────────────────────────────────────────────

export interface JobResponse {
  id: string;
  user_id: string;
  status: string;
  input_key: string;
  output_key: string | null;
  scale_factor: number;
  model_name: string;
  input_width: number;
  input_height: number;
  output_width: number | null;
  output_height: number | null;
  gpu_backend: string | null;
  progress: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface UploadResponse {
  key: string;
  filename: string;
  size: number;
  content_type: string;
}

export interface JobCreateParams {
  input_key: string;
  scale_factor?: number;
  model_name?: string;
}

export interface UserResponse {
  id: string;
  email: string;
  name: string | null;
  created_at: string;
}

export interface HealthResponse {
  status: string;
  version?: string;
  checks?: Record<string, string>;
}

// ── Helpers ──────────────────────────────────────────────────

const AUTH_TOKEN = import.meta.env.VITE_DEV_TOKEN ?? "dev-secret-token-change-me";

function headers(): HeadersInit {
  return {
    Authorization: `Bearer ${AUTH_TOKEN}`,
    "Content-Type": "application/json",
  };
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// ── Uploads ──────────────────────────────────────────────────

export async function uploadImage(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/uploads`, {
    method: "POST",
    headers: { Authorization: `Bearer ${AUTH_TOKEN}` },
    body: form,
  });

  return handleResponse<UploadResponse>(res);
}

// ── Jobs ─────────────────────────────────────────────────────

export async function createJob(
  params: JobCreateParams,
): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(params),
  });
  return handleResponse<JobResponse>(res);
}

export async function listJobs(): Promise<JobResponse[]> {
  const res = await fetch(`${API_BASE}/jobs`, { headers: headers() });
  return handleResponse<JobResponse[]>(res);
}

export async function getJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`, {
    headers: headers(),
  });
  return handleResponse<JobResponse>(res);
}

export async function cancelJob(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`, {
    method: "DELETE",
    headers: headers(),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
}

// ── Download ─────────────────────────────────────────────────

export function getDownloadUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/download`;
}

// ── Users ────────────────────────────────────────────────────

export async function getCurrentUser(): Promise<UserResponse> {
  const res = await fetch(`${API_BASE}/users/me`, { headers: headers() });
  return handleResponse<UserResponse>(res);
}

// ── Health ───────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  return handleResponse<HealthResponse>(res);
}

export async function getReadiness(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health/ready`);
  if (!res.ok) {
    // 503 : on récupère quand même le body pour afficher les détails.
    const body = await res.json().catch(() => ({}));
    return { status: "unhealthy", ...(body.detail ?? body) };
  }
  return res.json() as Promise<HealthResponse>;
}

