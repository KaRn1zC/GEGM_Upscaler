import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import {
  ImageUp,
  Layers,
  GalleryHorizontal,
  Clock,
  Settings,
  Sparkles,
} from "lucide-react";

// Note : useGlobalShortcuts a été déplacé dans @/hooks/useGlobalShortcuts
// pour que ce composant puisse être lazy-chargé sans bloquer l'App.

/**
 * Palette de commandes globale — ouverte via Cmd+K / Ctrl+K.
 *
 * Fournit une navigation rapide entre les 5 pages principales et
 * les actions fréquentes. Inspirée du pattern VS Code / Linear.
 */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const runCommand = (command: () => void) => {
    setOpen(false);
    // Laisse le dialog se fermer proprement avant la navigation.
    setTimeout(command, 80);
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title="Palette de commandes"
      description="Navigation rapide et actions"
    >
      <Command>
        <CommandInput placeholder="Rechercher une commande..." />
        <CommandList>
          <CommandEmpty>Aucun résultat.</CommandEmpty>

          <CommandGroup heading="Navigation">
            <CommandItem onSelect={() => runCommand(() => navigate("/upscale"))}>
              <ImageUp className="w-4 h-4" strokeWidth={1.8} />
              <span>Upscaler</span>
              <CommandShortcut>⌘1</CommandShortcut>
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => navigate("/batch"))}>
              <Layers className="w-4 h-4" strokeWidth={1.8} />
              <span>Batch</span>
              <CommandShortcut>⌘2</CommandShortcut>
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => navigate("/gallery"))}>
              <GalleryHorizontal className="w-4 h-4" strokeWidth={1.8} />
              <span>Galerie</span>
              <CommandShortcut>⌘3</CommandShortcut>
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => navigate("/history"))}>
              <Clock className="w-4 h-4" strokeWidth={1.8} />
              <span>Historique</span>
              <CommandShortcut>⌘4</CommandShortcut>
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => navigate("/settings"))}>
              <Settings className="w-4 h-4" strokeWidth={1.8} />
              <span>Paramètres</span>
              <CommandShortcut>⌘5</CommandShortcut>
            </CommandItem>
          </CommandGroup>

          <CommandSeparator />

          <CommandGroup heading="Actions rapides">
            <CommandItem onSelect={() => runCommand(() => navigate("/upscale"))}>
              <Sparkles className="w-4 h-4" strokeWidth={1.8} />
              <span>Nouvel upscale</span>
              <CommandShortcut>⌘U</CommandShortcut>
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => navigate("/batch"))}>
              <Layers className="w-4 h-4" strokeWidth={1.8} />
              <span>Nouveau batch</span>
              <CommandShortcut>⌘B</CommandShortcut>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}

// Default export requis par React.lazy().
export default CommandPalette;
