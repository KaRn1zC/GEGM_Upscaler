import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DropZone } from "./DropZone";

// jsdom ne fournit pas URL.createObjectURL — on le stub avant chaque test.
beforeEach(() => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:fake-url"),
    revokeObjectURL: vi.fn(),
  });
});

describe("DropZone", () => {
  it("should render initial state with instructions", () => {
    render(<DropZone onFileAccepted={() => {}} />);
    expect(screen.getByText(/Glisser une image/)).toBeInTheDocument();
    expect(screen.getByText(/PNG, JPEG, WebP, TIFF/)).toBeInTheDocument();
  });

  it("should accept a valid image file via click", async () => {
    const user = userEvent.setup();
    const onFileAccepted = vi.fn();

    const { container } = render(<DropZone onFileAccepted={onFileAccepted} />);

    const file = new File(["image data"], "photo.png", { type: "image/png" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(input, file);

    await waitFor(() => {
      expect(onFileAccepted).toHaveBeenCalledWith(file);
    });
  });

  it("should show file preview after selection", async () => {
    const user = userEvent.setup();
    const { container } = render(<DropZone onFileAccepted={vi.fn()} />);

    const file = new File(["data"], "sunset.png", { type: "image/png" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText("sunset.png")).toBeInTheDocument();
    });
    expect(screen.getByRole("img")).toHaveAttribute("src", "blob:fake-url");
  });

  it("should format file size correctly for KB", async () => {
    const user = userEvent.setup();
    const { container } = render(<DropZone onFileAccepted={vi.fn()} />);

    // 500 bytes → affiché en Ko.
    const smallFile = new File([new Uint8Array(500)], "tiny.png", { type: "image/png" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(input, smallFile);

    await waitFor(() => {
      expect(screen.getByText(/Ko/)).toBeInTheDocument();
    });
  });

  it("should format file size correctly for MB", async () => {
    const user = userEvent.setup();
    const { container } = render(<DropZone onFileAccepted={vi.fn()} />);

    // 2 Mo.
    const bigFile = new File([new Uint8Array(2 * 1024 * 1024)], "big.png", {
      type: "image/png",
    });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(input, bigFile);

    await waitFor(() => {
      expect(screen.getByText(/2\.0 Mo/)).toBeInTheDocument();
    });
  });

  it("should clear preview when X button is clicked", async () => {
    const user = userEvent.setup();
    const { container } = render(<DropZone onFileAccepted={vi.fn()} />);

    const file = new File(["data"], "photo.png", { type: "image/png" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(input, file);

    await waitFor(() => expect(screen.getByText("photo.png")).toBeInTheDocument());

    // Le bouton X n'a pas de label textuel — on le cible via le SVG parent.
    const closeButton = container.querySelector(
      'button[class*="bg-white/10"]',
    ) as HTMLButtonElement;
    expect(closeButton).not.toBeNull();

    await user.click(closeButton);

    await waitFor(() => {
      expect(screen.queryByText("photo.png")).not.toBeInTheDocument();
    });
    expect(screen.getByText(/Glisser une image/)).toBeInTheDocument();
  });

  it("should apply disabled visual state when disabled prop is true", () => {
    const { container } = render(<DropZone onFileAccepted={vi.fn()} disabled />);
    // react-dropzone ne désactive pas l'input mais applique nos classes visuelles.
    const dropzone = container.querySelector('[class*="cursor-not-allowed"]');
    expect(dropzone).not.toBeNull();
  });

  it("should show max file size in the placeholder", () => {
    render(<DropZone onFileAccepted={vi.fn()} />);
    // Default MAX_FILE_SIZE_MB = 200.
    expect(screen.getByText(/200 Mo max/)).toBeInTheDocument();
  });
});
