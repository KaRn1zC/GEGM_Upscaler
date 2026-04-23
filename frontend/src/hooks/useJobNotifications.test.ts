import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useJobNotifications } from "./useJobNotifications";
import { useJobStore } from "@/stores/useJobStore";
import type { JobResponse } from "@/lib/api";

const notificationMocks = {
  isPermissionGranted: vi.fn<() => Promise<boolean>>(),
  requestPermission: vi.fn<() => Promise<"granted" | "denied" | "default">>(),
  sendNotification: vi.fn(),
};

vi.mock("@tauri-apps/plugin-notification", () => notificationMocks);

vi.mock("@/lib/tauri", async () => {
  const actual = await vi.importActual<typeof import("@/lib/tauri")>("@/lib/tauri");
  return {
    ...actual,
    isTauri: vi.fn(() => true),
  };
});

function makeJob(overrides: Partial<JobResponse> = {}): JobResponse {
  return {
    id: overrides.id ?? "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    user_id: "user-1",
    input_key: "uploads/a.png",
    scale_factor: 2,
    status: "queued",
    progress: 0.0,
    model_name: "drct-l",
    prefer_local: null,
    output_key: null,
    error_message: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    completed_at: null,
    ...overrides,
  } as JobResponse;
}

describe("useJobNotifications", () => {
  beforeEach(() => {
    notificationMocks.isPermissionGranted.mockReset();
    notificationMocks.requestPermission.mockReset();
    notificationMocks.sendNotification.mockReset();
    notificationMocks.isPermissionGranted.mockResolvedValue(true);
    notificationMocks.requestPermission.mockResolvedValue("granted");
    // Reset store state
    useJobStore.setState({ jobs: [], isLoading: false });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should skip permission request when already granted", async () => {
    renderHook(() => useJobNotifications());
    await waitFor(() =>
      expect(notificationMocks.isPermissionGranted).toHaveBeenCalled(),
    );
    expect(notificationMocks.requestPermission).not.toHaveBeenCalled();
  });

  it("should request permission when not yet granted", async () => {
    notificationMocks.isPermissionGranted.mockResolvedValue(false);
    notificationMocks.requestPermission.mockResolvedValue("granted");
    renderHook(() => useJobNotifications());
    await waitFor(() =>
      expect(notificationMocks.requestPermission).toHaveBeenCalledTimes(1),
    );
  });

  it("should send a notification when a job transitions processing → completed", async () => {
    renderHook(() => useJobNotifications());

    // Attendre que la permission soit résolue (sinon permissionGranted=false
    // et la notif est skip même si le store change).
    await waitFor(() =>
      expect(notificationMocks.isPermissionGranted).toHaveBeenCalled(),
    );

    const job = makeJob({ id: "job-complete-id", status: "processing" });
    act(() => useJobStore.setState({ jobs: [job] }));
    act(() =>
      useJobStore.setState({
        jobs: [{ ...job, status: "completed", output_key: "out/a.png" }],
      }),
    );

    await waitFor(() =>
      expect(notificationMocks.sendNotification).toHaveBeenCalledTimes(1),
    );

    const call = notificationMocks.sendNotification.mock.calls[0][0] as {
      title: string;
      body: string;
    };
    expect(call.title).toMatch(/Upscale terminé/);
    expect(call.body).toContain("job-comp");
  });

  it("should send a failure notification when a job transitions to failed", async () => {
    renderHook(() => useJobNotifications());
    await waitFor(() =>
      expect(notificationMocks.isPermissionGranted).toHaveBeenCalled(),
    );

    const job = makeJob({ id: "job-fail-id", status: "processing" });
    act(() => useJobStore.setState({ jobs: [job] }));
    act(() =>
      useJobStore.setState({
        jobs: [{ ...job, status: "failed", error_message: "boom" }],
      }),
    );

    await waitFor(() =>
      expect(notificationMocks.sendNotification).toHaveBeenCalledTimes(1),
    );
    const call = notificationMocks.sendNotification.mock.calls[0][0] as {
      title: string;
    };
    expect(call.title).toMatch(/échoué/);
  });

  it("should not notify when permission is denied", async () => {
    notificationMocks.isPermissionGranted.mockResolvedValue(false);
    notificationMocks.requestPermission.mockResolvedValue("denied");

    renderHook(() => useJobNotifications());
    await waitFor(() =>
      expect(notificationMocks.requestPermission).toHaveBeenCalled(),
    );

    const job = makeJob({ id: "job-denied", status: "processing" });
    act(() => useJobStore.setState({ jobs: [job] }));
    act(() =>
      useJobStore.setState({
        jobs: [{ ...job, status: "completed", output_key: "out/a.png" }],
      }),
    );

    // Laisser passer un tick de réaction au store
    await new Promise((r) => setTimeout(r, 20));
    expect(notificationMocks.sendNotification).not.toHaveBeenCalled();
  });

  it("should not notify on initial mount when jobs start already completed", async () => {
    // Seed un job completed AVANT le mount — pas de transition "processing → completed"
    // observable puisqu'on n'a pas de previousStatus.
    const job = makeJob({ id: "job-seed", status: "completed" });
    useJobStore.setState({ jobs: [job] });

    renderHook(() => useJobNotifications());
    await waitFor(() =>
      expect(notificationMocks.isPermissionGranted).toHaveBeenCalled(),
    );

    await new Promise((r) => setTimeout(r, 20));
    expect(notificationMocks.sendNotification).not.toHaveBeenCalled();
  });
});

describe("useJobNotifications outside Tauri", () => {
  beforeEach(async () => {
    const tauri = await import("@/lib/tauri");
    vi.mocked(tauri.isTauri).mockReturnValue(false);
    notificationMocks.isPermissionGranted.mockReset();
    notificationMocks.sendNotification.mockReset();
    useJobStore.setState({ jobs: [] });
  });

  afterEach(async () => {
    const tauri = await import("@/lib/tauri");
    vi.mocked(tauri.isTauri).mockReturnValue(true);
  });

  it("should be a complete no-op (no permission check, no notification)", async () => {
    renderHook(() => useJobNotifications());

    const job = makeJob({ status: "processing" });
    act(() => useJobStore.setState({ jobs: [job] }));
    act(() =>
      useJobStore.setState({
        jobs: [{ ...job, status: "completed", output_key: "out/a.png" }],
      }),
    );

    await new Promise((r) => setTimeout(r, 20));
    expect(notificationMocks.isPermissionGranted).not.toHaveBeenCalled();
    expect(notificationMocks.sendNotification).not.toHaveBeenCalled();
  });
});
