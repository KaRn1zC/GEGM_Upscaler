import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUpdaterStore } from "./useUpdaterStore";

type DownloadEvent =
  | { event: "Started"; data: { contentLength?: number } }
  | { event: "Progress"; data: { chunkLength: number } }
  | { event: "Finished" };

interface UpdateMock {
  version: string;
  currentVersion: string;
  body?: string;
  date?: string;
  downloadAndInstall: (cb: (event: DownloadEvent) => void) => Promise<void>;
}

const updaterMocks = {
  check: vi.fn<() => Promise<UpdateMock | null>>(),
};

const processMocks = {
  relaunch: vi.fn<() => Promise<void>>(),
};

vi.mock("@tauri-apps/plugin-updater", () => updaterMocks);
vi.mock("@tauri-apps/plugin-process", () => processMocks);

vi.mock("@/lib/tauri", async () => {
  const actual = await vi.importActual<typeof import("@/lib/tauri")>("@/lib/tauri");
  return {
    ...actual,
    isTauri: vi.fn(() => true),
  };
});

function resetStore(): void {
  useUpdaterStore.setState({
    phase: "idle",
    update: null,
    progress: { downloaded: 0, total: 0 },
    error: null,
    checkedOnce: false,
  });
}

describe("useUpdaterStore.checkNow", () => {
  beforeEach(() => {
    resetStore();
    updaterMocks.check.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should transition to 'available' when an update is found", async () => {
    updaterMocks.check.mockResolvedValue({
      version: "0.2.0",
      currentVersion: "0.1.0",
      body: "Bug fixes",
      date: "2026-04-23",
      downloadAndInstall: vi.fn(),
    });

    await act(async () => {
      await useUpdaterStore.getState().checkNow();
    });

    const state = useUpdaterStore.getState();
    expect(state.phase).toBe("available");
    expect(state.update).toMatchObject({ version: "0.2.0", currentVersion: "0.1.0" });
    expect(state.checkedOnce).toBe(true);
  });

  it("should transition back to 'idle' when no update is available", async () => {
    updaterMocks.check.mockResolvedValue(null);

    await act(async () => {
      await useUpdaterStore.getState().checkNow();
    });

    const state = useUpdaterStore.getState();
    expect(state.phase).toBe("idle");
    expect(state.update).toBeNull();
    expect(state.checkedOnce).toBe(true);
  });

  it("should capture the error message when check throws", async () => {
    updaterMocks.check.mockRejectedValue(new Error("network down"));

    await act(async () => {
      await useUpdaterStore.getState().checkNow();
    });

    const state = useUpdaterStore.getState();
    expect(state.phase).toBe("error");
    expect(state.error).toBe("network down");
  });
});

describe("useUpdaterStore.installAndRestart", () => {
  beforeEach(() => {
    resetStore();
    updaterMocks.check.mockReset();
    processMocks.relaunch.mockReset();
    processMocks.relaunch.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should walk through downloading → installing and call relaunch", async () => {
    updaterMocks.check.mockResolvedValue({
      version: "0.2.0",
      currentVersion: "0.1.0",
      downloadAndInstall: async (cb) => {
        cb({ event: "Started", data: { contentLength: 1000 } });
        cb({ event: "Progress", data: { chunkLength: 400 } });
        cb({ event: "Progress", data: { chunkLength: 600 } });
        cb({ event: "Finished" });
      },
    });

    await act(async () => {
      await useUpdaterStore.getState().installAndRestart();
    });

    const state = useUpdaterStore.getState();
    expect(state.phase).toBe("installing");
    expect(state.progress.total).toBe(1000);
    expect(state.progress.downloaded).toBe(1000);
    expect(processMocks.relaunch).toHaveBeenCalledTimes(1);
  });

  it("should go back to idle when no update is actually available", async () => {
    updaterMocks.check.mockResolvedValue(null);

    await act(async () => {
      await useUpdaterStore.getState().installAndRestart();
    });

    expect(useUpdaterStore.getState().phase).toBe("idle");
    expect(processMocks.relaunch).not.toHaveBeenCalled();
  });

  it("should transition to 'error' when downloadAndInstall throws", async () => {
    updaterMocks.check.mockResolvedValue({
      version: "0.2.0",
      currentVersion: "0.1.0",
      downloadAndInstall: async () => {
        throw new Error("disk full");
      },
    });

    await act(async () => {
      await useUpdaterStore.getState().installAndRestart();
    });

    const state = useUpdaterStore.getState();
    expect(state.phase).toBe("error");
    expect(state.error).toBe("disk full");
    expect(processMocks.relaunch).not.toHaveBeenCalled();
  });
});

describe("useUpdaterStore.dismiss", () => {
  beforeEach(resetStore);

  it("should clear the update and go back to idle", () => {
    useUpdaterStore.setState({
      phase: "available",
      update: { version: "0.2.0", currentVersion: "0.1.0" },
    });
    act(() => useUpdaterStore.getState().dismiss());
    const state = useUpdaterStore.getState();
    expect(state.phase).toBe("idle");
    expect(state.update).toBeNull();
  });
});

describe("useUpdaterStore outside Tauri", () => {
  beforeEach(async () => {
    resetStore();
    updaterMocks.check.mockReset();
    processMocks.relaunch.mockReset();
    const tauri = await import("@/lib/tauri");
    vi.mocked(tauri.isTauri).mockReturnValue(false);
  });

  afterEach(async () => {
    const tauri = await import("@/lib/tauri");
    vi.mocked(tauri.isTauri).mockReturnValue(true);
  });

  it("should make checkNow a no-op (no plugin import, state untouched)", async () => {
    await act(async () => {
      await useUpdaterStore.getState().checkNow();
    });
    expect(updaterMocks.check).not.toHaveBeenCalled();
    expect(useUpdaterStore.getState().phase).toBe("idle");
  });

  it("should make installAndRestart a no-op (no relaunch)", async () => {
    await act(async () => {
      await useUpdaterStore.getState().installAndRestart();
    });
    expect(processMocks.relaunch).not.toHaveBeenCalled();
  });
});
