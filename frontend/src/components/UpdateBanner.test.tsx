import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LazyMotion, domMax } from "motion/react";
import { UpdateBanner } from "./UpdateBanner";
import { useUpdaterStore } from "@/stores/useUpdaterStore";

vi.mock("@/lib/tauri", async () => {
  const actual = await vi.importActual<typeof import("@/lib/tauri")>("@/lib/tauri");
  return {
    ...actual,
    isTauri: vi.fn(() => true),
  };
});

vi.mock("@tauri-apps/plugin-updater", () => ({
  check: vi.fn().mockResolvedValue(null),
}));

vi.mock("@tauri-apps/plugin-process", () => ({
  relaunch: vi.fn().mockResolvedValue(undefined),
}));

function renderBanner() {
  return render(
    <LazyMotion features={domMax} strict>
      <UpdateBanner />
    </LazyMotion>,
  );
}

describe("UpdateBanner", () => {
  beforeEach(() => {
    useUpdaterStore.setState({
      phase: "idle",
      update: null,
      progress: { downloaded: 0, total: 0 },
      error: null,
      checkedOnce: true, // skip l'auto-check qu'on teste déjà dans useUpdater
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should not render anything when phase is idle", () => {
    renderBanner();
    expect(screen.queryByText(/Mise à jour/i)).not.toBeInTheDocument();
  });

  it("should show the available update card with version diff", () => {
    act(() =>
      useUpdaterStore.setState({
        phase: "available",
        update: {
          version: "0.2.0",
          currentVersion: "0.1.0",
          body: "Bug fixes and perf",
        },
      }),
    );
    renderBanner();
    expect(screen.getByText("Mise à jour disponible")).toBeInTheDocument();
    expect(screen.getByText(/v0.1.0.+v0.2.0/)).toBeInTheDocument();
    expect(screen.getByText(/Bug fixes and perf/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Installer et relancer/i }),
    ).toBeInTheDocument();
  });

  it("should trigger installAndRestart on click", async () => {
    const user = userEvent.setup();
    const install = vi.fn().mockResolvedValue(undefined);

    act(() =>
      useUpdaterStore.setState({
        phase: "available",
        update: { version: "0.2.0", currentVersion: "0.1.0" },
        installAndRestart: install,
      }),
    );

    renderBanner();
    await user.click(screen.getByRole("button", { name: /Installer et relancer/i }));
    expect(install).toHaveBeenCalledTimes(1);
  });

  it("should dismiss on X click", async () => {
    const user = userEvent.setup();
    act(() =>
      useUpdaterStore.setState({
        phase: "available",
        update: { version: "0.2.0", currentVersion: "0.1.0" },
      }),
    );

    renderBanner();
    await user.click(screen.getByRole("button", { name: /Ignorer la notification/i }));

    expect(useUpdaterStore.getState().phase).toBe("idle");
  });

  it("should show a progress bar while downloading", () => {
    act(() =>
      useUpdaterStore.setState({
        phase: "downloading",
        update: { version: "0.2.0", currentVersion: "0.1.0" },
        progress: { downloaded: 5_000_000, total: 10_000_000 },
      }),
    );
    renderBanner();
    expect(screen.getByText(/Téléchargement de la mise à jour/i)).toBeInTheDocument();
    expect(screen.getByText(/5 \/ 10 MB.*50%/)).toBeInTheDocument();
  });

  it("should show 'Installation…' during installing phase", () => {
    act(() =>
      useUpdaterStore.setState({
        phase: "installing",
        update: { version: "0.2.0", currentVersion: "0.1.0" },
        progress: { downloaded: 100, total: 100 },
      }),
    );
    renderBanner();
    expect(screen.getByText(/Installation/)).toBeInTheDocument();
  });

  it("should show the error message when phase is error", () => {
    act(() =>
      useUpdaterStore.setState({
        phase: "error",
        error: "signature invalide",
      }),
    );
    renderBanner();
    expect(screen.getByText(/Échec de la mise à jour/i)).toBeInTheDocument();
    expect(screen.getByText(/signature invalide/)).toBeInTheDocument();
  });
});
