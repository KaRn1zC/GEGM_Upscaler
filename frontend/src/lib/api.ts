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
  prefer_local: boolean | null;
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
  prefer_local?: boolean | null;
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

/**
 * Récupère le token courant de façon synchrone pour construire les
 * headers/URLs. En mode `dev`, c'est le static `VITE_DEV_TOKEN` ; en
 * mode `oidc`, c'est l'accessToken stocké dans `useAuthStore` (peut
 * être "" si pas encore loggé).
 *
 * Pour les appels avec refresh automatique (préféré pour fetch), utiliser
 * `await useAuthStore.getState().getValidToken()`. Pour les URLs balises
 * HTML (<img>, <a download>, EventSource), on reste sur le token courant
 * car on ne peut pas attendre avant de le coller dans l'attribut.
 */
import { getCurrentAccessToken, useAuthStore } from "@/stores/useAuthStore";

async function headers(): Promise<HeadersInit> {
  const token = (await useAuthStore.getState().getValidToken()) ?? "";
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

/**
 * Ajoute le token d'authentification en query param à une URL d'API.
 *
 * Destiné aux contextes où les headers HTTP ne peuvent pas être contrôlés —
 * typiquement les balises HTML natives (`<img src>`, `<a download>`, `EventSource`).
 *
 * En prod OIDC, les JWT sont trop longs/sensibles pour être passés en URL ;
 * on basculera alors sur des presigned URLs générées par le StorageBackend S3
 * (qui n'ont plus besoin du token puisque l'accès est signé cryptographiquement).
 * Ce helper restera utilisable tel quel côté frontend — seule l'implémentation
 * backend changera (redirect 302 vers la presigned URL).
 */
function buildAuthedUrl(path: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}token=${encodeURIComponent(getCurrentAccessToken())}`;
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

  const token = (await useAuthStore.getState().getValidToken()) ?? "";
  const res = await fetch(`${API_BASE}/uploads`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
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
    headers: await headers(),
    body: JSON.stringify(params),
  });
  return handleResponse<JobResponse>(res);
}

export async function listJobs(): Promise<JobResponse[]> {
  const res = await fetch(`${API_BASE}/jobs`, { headers: await headers() });
  return handleResponse<JobResponse[]>(res);
}

export async function getJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`, {
    headers: await headers(),
  });
  return handleResponse<JobResponse>(res);
}

export async function cancelJob(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`, {
    method: "DELETE",
    headers: await headers(),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
}

// ── URLs authentifiées (pour <img>, <a download>, EventSource) ─────────

/**
 * URL du fichier résultat d'un job, utilisable directement dans un ``<img src>``
 * ou un ``window.open`` sans pouvoir injecter le header Authorization.
 */
export function getDownloadUrl(jobId: string): string {
  return buildAuthedUrl(`${API_BASE}/jobs/${jobId}/download`);
}

/**
 * URL du fichier source (input) d'un job, utilisable dans un ``<img src>``.
 *
 * ``inputKey`` vient de ``job.input_key`` et contient déjà le chemin
 * interne au bucket (ex. ``uploads/<uuid>.png``). Le préfixe ``/api/uploads/``
 * est celui de l'endpoint FastAPI — il est concaténé à la key pour former
 * l'URL complète ``/api/uploads/uploads/<uuid>.png``, où le second ``uploads/``
 * est le segment de clé (équivalent à un "dossier" dans le bucket).
 */
export function getUploadUrl(inputKey: string): string {
  return buildAuthedUrl(`${API_BASE}/uploads/${inputKey}`);
}

/**
 * URL du stream SSE de progression d'un job, utilisable dans un ``EventSource``.
 *
 * ``EventSource`` ne supporte pas les headers custom — on passe donc le token
 * en query param comme pour les autres URLs authentifiées.
 */
export function getProgressStreamUrl(jobId: string): string {
  return buildAuthedUrl(`${API_BASE}/jobs/${jobId}/progress`);
}

// ── Users ────────────────────────────────────────────────────

export async function getCurrentUser(): Promise<UserResponse> {
  const res = await fetch(`${API_BASE}/users/me`, { headers: await headers() });
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

