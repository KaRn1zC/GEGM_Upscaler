import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ZoomViewer } from "./ZoomViewer";

describe("ZoomViewer", () => {
  const url = "/test.png";

  it("should render the image with the provided URL", () => {
    render(<ZoomViewer imageUrl={url} />);
    const img = screen.getByRole("img");
    expect(img.getAttribute("src")).toBe(url);
  });

  it("should use the title as alt text when provided", () => {
    render(<ZoomViewer imageUrl={url} title="Mon image" />);
    expect(screen.getByAltText("Mon image")).toBeInTheDocument();
  });

  it("should fall back to generic alt when title is absent", () => {
    render(<ZoomViewer imageUrl={url} />);
    expect(screen.getByAltText("Image")).toBeInTheDocument();
  });

  it("should display the title in the floating label", () => {
    render(<ZoomViewer imageUrl={url} title="4096×2160" />);
    expect(screen.getByText("4096×2160")).toBeInTheDocument();
  });

  it("should render zoom in/out/reset buttons via tooltips", () => {
    render(<ZoomViewer imageUrl={url} />);
    expect(screen.getByTitle("Zoom avant")).toBeInTheDocument();
    expect(screen.getByTitle("Zoom arrière")).toBeInTheDocument();
    expect(screen.getByTitle("Réinitialiser")).toBeInTheDocument();
  });

  it("should render close button only when onClose is provided", () => {
    const { rerender } = render(<ZoomViewer imageUrl={url} />);
    expect(screen.queryByLabelText("Fermer le viewer")).not.toBeInTheDocument();

    rerender(<ZoomViewer imageUrl={url} onClose={vi.fn()} />);
    expect(screen.getByLabelText("Fermer le viewer")).toBeInTheDocument();
  });

  it("should call onClose when close button is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<ZoomViewer imageUrl={url} onClose={onClose} />);
    await user.click(screen.getByLabelText("Fermer le viewer"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("should render the keyboard/mouse hint", () => {
    render(<ZoomViewer imageUrl={url} />);
    expect(screen.getByText(/Molette · Glisser · Double-clic/i)).toBeInTheDocument();
  });

  it("should have draggable=false on the image to avoid browser drag-and-drop", () => {
    render(<ZoomViewer imageUrl={url} />);
    const img = screen.getByRole("img");
    expect(img.getAttribute("draggable")).toBe("false");
  });
});
