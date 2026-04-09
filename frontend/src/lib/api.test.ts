import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cancelJob,
  createJob,
  getCurrentUser,
  getDownloadUrl,
  listJobs,
  uploadImage,
} from "./api";

// Mock global de fetch — restauré après chaque test.
const mockFetch = vi.fn();

beforeEach(() => {
  mockFetch.mockReset();
  vi.stubGlobal("fetch", mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * Construit une Response mockée avec un body JSON.
 */
function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("getDownloadUrl", () => {
  it("should build the correct download path", () => {
    expect(getDownloadUrl("job-123")).toBe("/api/jobs/job-123/download");
  });

  it("should handle UUID-like job IDs", () => {
    expect(getDownloadUrl("a1b2c3d4-5678")).toBe("/api/jobs/a1b2c3d4-5678/download");
  });
});

describe("uploadImage", () => {
  it("should POST the file as multipart/form-data", async () => {
    const file = new File(["fake-data"], "photo.png", { type: "image/png" });
    mockFetch.mockResolvedValueOnce(
      jsonResponse({
        key: "uploads/abc.png",
        filename: "photo.png",
        size: 9,
        content_type: "image/png",
      }),
    );

    const result = await uploadImage(file);

    expect(result.key).toBe("uploads/abc.png");
    expect(mockFetch).toHaveBeenCalledOnce();

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/uploads");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBeInstanceOf(FormData);
  });

  it("should throw on HTTP error", async () => {
    const file = new File(["data"], "bad.png", { type: "image/png" });
    mockFetch.mockResolvedValueOnce(
      new Response("Format non supporté", { status: 400 }),
    );

    await expect(uploadImage(file)).rejects.toThrow(/HTTP 400/);
  });
});

describe("createJob", () => {
  it("should POST the job params as JSON with auth header", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({
        id: "job-1",
        user_id: "user-1",
        status: "pending",
        input_key: "uploads/abc.png",
        output_key: null,
        scale_factor: 4,
        model_name: "drct-l",
        input_width: 100,
        input_height: 100,
        output_width: null,
        output_height: null,
        gpu_backend: null,
        progress: 0,
        error_message: null,
        created_at: "2026-04-09T00:00:00Z",
        updated_at: "2026-04-09T00:00:00Z",
        completed_at: null,
      }),
    );

    const job = await createJob({ input_key: "uploads/abc.png", scale_factor: 4 });

    expect(job.id).toBe("job-1");
    const [, init] = mockFetch.mock.calls[0];
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toMatch(/^Bearer /);
    expect(headers["Content-Type"]).toBe("application/json");
    expect((init as RequestInit).body).toBe(
      JSON.stringify({ input_key: "uploads/abc.png", scale_factor: 4 }),
    );
  });
});

describe("listJobs", () => {
  it("should GET /api/jobs and return an array", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([]));
    const jobs = await listJobs();
    expect(jobs).toEqual([]);
    expect(mockFetch).toHaveBeenCalledWith("/api/jobs", expect.any(Object));
  });
});

describe("cancelJob", () => {
  it("should send DELETE request", async () => {
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await cancelJob("job-42");

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/jobs/job-42");
    expect((init as RequestInit).method).toBe("DELETE");
  });

  it("should throw on error response", async () => {
    mockFetch.mockResolvedValueOnce(new Response("Conflit", { status: 409 }));
    await expect(cancelJob("job-x")).rejects.toThrow(/HTTP 409/);
  });
});

describe("getCurrentUser", () => {
  it("should GET /api/users/me and return the user", async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({
        id: "user-123",
        email: "alice@gegm.com",
        name: "Alice",
        created_at: "2026-01-01T00:00:00Z",
      }),
    );

    const user = await getCurrentUser();

    expect(user.email).toBe("alice@gegm.com");
    expect(mockFetch).toHaveBeenCalledWith("/api/users/me", expect.any(Object));
  });
});
