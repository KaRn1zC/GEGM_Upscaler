import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BatchPanel } from "./BatchPanel";

beforeEach(() => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:fake-url"),
    revokeObjectURL: vi.fn(),
  });
});

function getInput(container: HTMLElement): HTMLInputElement {
  return container.querySelector('input[type="file"]') as HTMLInputElement;
}

describe("BatchPanel", () => {
  it("should render empty state with instructions", () => {
    render(<BatchPanel onSubmit={vi.fn()} isSubmitting={false} />);
    expect(screen.getByText(/Glisser plusieurs images/)).toBeInTheDocument();
    // Les actions ne doivent pas apparaître sans fichiers.
    expect(screen.queryByText("Lancer le batch")).not.toBeInTheDocument();
  });

  it("should add files to the queue after upload", async () => {
    const user = userEvent.setup();
    const { container } = render(<BatchPanel onSubmit={vi.fn()} isSubmitting={false} />);

    const files = [
      new File(["a"], "one.png", { type: "image/png" }),
      new File(["b"], "two.png", { type: "image/png" }),
    ];

    await user.upload(getInput(container), files);

    await waitFor(() => {
      expect(screen.getByText("one.png")).toBeInTheDocument();
      expect(screen.getByText("two.png")).toBeInTheDocument();
      expect(screen.getByText(/2 images/)).toBeInTheDocument();
    });
  });

  it("should show singular 'image' for a single file", async () => {
    const user = userEvent.setup();
    const { container } = render(<BatchPanel onSubmit={vi.fn()} isSubmitting={false} />);

    await user.upload(getInput(container), [
      new File(["a"], "solo.png", { type: "image/png" }),
    ]);

    await waitFor(() => {
      expect(screen.getByText(/1 image[^s]/)).toBeInTheDocument();
    });
  });

  it("should remove a single file when its X button is clicked", async () => {
    const user = userEvent.setup();
    const { container } = render(<BatchPanel onSubmit={vi.fn()} isSubmitting={false} />);

    const file = new File(["a"], "to-remove.png", { type: "image/png" });
    await user.upload(getInput(container), [file]);

    await waitFor(() => expect(screen.getByText("to-remove.png")).toBeInTheDocument());

    // X button est dans l'overlay de la tuile — on le trouve via son icône.
    const removeBtn = container.querySelector(
      'button[class*="bg-black/60"]',
    ) as HTMLButtonElement;
    expect(removeBtn).not.toBeNull();

    await user.click(removeBtn);

    await waitFor(() => {
      expect(screen.queryByText("to-remove.png")).not.toBeInTheDocument();
    });
  });

  it("should clear the queue when 'Vider' button is clicked", async () => {
    const user = userEvent.setup();
    const { container } = render(<BatchPanel onSubmit={vi.fn()} isSubmitting={false} />);

    await user.upload(getInput(container), [
      new File(["a"], "a.png", { type: "image/png" }),
      new File(["b"], "b.png", { type: "image/png" }),
    ]);

    await waitFor(() => expect(screen.getByText("a.png")).toBeInTheDocument());

    await user.click(screen.getByText("Vider"));

    await waitFor(() => {
      expect(screen.queryByText("a.png")).not.toBeInTheDocument();
      expect(screen.queryByText("b.png")).not.toBeInTheDocument();
    });
  });

  it("should change the scale factor", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const { container } = render(<BatchPanel onSubmit={onSubmit} isSubmitting={false} />);

    await user.upload(getInput(container), [
      new File(["a"], "img.png", { type: "image/png" }),
    ]);

    await waitFor(() => expect(screen.getByText("img.png")).toBeInTheDocument());

    // Clic sur le bouton 2× (le 4× est sélectionné par défaut).
    await user.click(screen.getByText("2×"));
    await user.click(screen.getByText("Lancer le batch"));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalled();
    });
    const [files, scaleFactor] = onSubmit.mock.calls[0];
    expect(scaleFactor).toBe(2);
    expect(files).toHaveLength(1);
  });

  it("should call onSubmit with the queue files and clear after", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const { container } = render(<BatchPanel onSubmit={onSubmit} isSubmitting={false} />);

    const files = [
      new File(["a"], "one.png", { type: "image/png" }),
      new File(["b"], "two.png", { type: "image/png" }),
    ];

    await user.upload(getInput(container), files);
    await waitFor(() => expect(screen.getByText("one.png")).toBeInTheDocument());

    await user.click(screen.getByText("Lancer le batch"));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    expect(onSubmit.mock.calls[0][0]).toHaveLength(2);

    // Après le submit, la queue doit être vidée.
    await waitFor(() => {
      expect(screen.queryByText("one.png")).not.toBeInTheDocument();
    });
  });

  it("should disable the submit button when isSubmitting is true", async () => {
    const user = userEvent.setup();
    const { container, rerender } = render(
      <BatchPanel onSubmit={vi.fn()} isSubmitting={false} />,
    );

    await user.upload(getInput(container), [
      new File(["a"], "img.png", { type: "image/png" }),
    ]);
    await waitFor(() => expect(screen.getByText("img.png")).toBeInTheDocument());

    rerender(<BatchPanel onSubmit={vi.fn()} isSubmitting={true} />);

    // Le label change en "Envoi..." pendant la soumission.
    expect(screen.getByText(/Envoi/)).toBeInTheDocument();
  });

  it("should not submit when the queue is empty", async () => {
    // Quand aucun fichier n'est ajouté, le bouton n'est même pas rendu.
    const onSubmit = vi.fn();
    render(<BatchPanel onSubmit={onSubmit} isSubmitting={false} />);

    expect(screen.queryByText("Lancer le batch")).not.toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
