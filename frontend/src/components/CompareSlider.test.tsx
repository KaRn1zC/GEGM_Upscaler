import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CompareSlider } from "./CompareSlider";

describe("CompareSlider", () => {
  const before = "/before.png";
  const after = "/after.png";

  it("should render both images", () => {
    render(<CompareSlider beforeSrc={before} afterSrc={after} />);
    const images = screen.getAllByRole("img");
    expect(images.length).toBeGreaterThanOrEqual(2);
    // Les sources peuvent être dupliquées par react-compare-slider (pré-chargement),
    // on s'assure juste que les deux URLs sont présentes dans le DOM.
    const srcs = images.map((img) => img.getAttribute("src"));
    expect(srcs).toContain(before);
    expect(srcs).toContain(after);
  });

  it("should use default French labels when none provided", () => {
    render(<CompareSlider beforeSrc={before} afterSrc={after} />);
    expect(screen.getByText("Original")).toBeInTheDocument();
    expect(screen.getByText("Upscalé")).toBeInTheDocument();
  });

  it("should use custom labels when provided", () => {
    render(
      <CompareSlider
        beforeSrc={before}
        afterSrc={after}
        beforeLabel="Avant"
        afterLabel="Après"
      />,
    );
    expect(screen.getByText("Avant")).toBeInTheDocument();
    expect(screen.getByText("Après")).toBeInTheDocument();
  });

  it("should not render the close button when onClose is undefined", () => {
    render(<CompareSlider beforeSrc={before} afterSrc={after} />);
    expect(screen.queryByLabelText("Fermer la comparaison")).not.toBeInTheDocument();
  });

  it("should render close button and call onClose when clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<CompareSlider beforeSrc={before} afterSrc={after} onClose={onClose} />);

    const btn = screen.getByLabelText("Fermer la comparaison");
    await user.click(btn);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("should render the drag hint", () => {
    render(<CompareSlider beforeSrc={before} afterSrc={after} />);
    expect(screen.getByText(/Glisser pour comparer/i)).toBeInTheDocument();
  });
});
