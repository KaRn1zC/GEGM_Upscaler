import { createContext, useContext } from "react";

/**
 * Options d'une demande de confirmation.
 *
 * `destructive` colore le bouton d'action en rouge (suppression) — vrai par
 * défaut puisque le seul usage actuel est la suppression de jobs.
 */
export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
}

export type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

/** Fallback hors `<ConfirmProvider>` : confirmation native du navigateur.
 *  L'app monte toujours le provider (dialog riche) ; ce défaut évite qu'un
 *  composant rendu isolément (tests, Storybook) casse au `useConfirm`. */
const nativeConfirm: ConfirmFn = async (options) =>
  typeof window !== "undefined" && typeof window.confirm === "function"
    ? window.confirm(options.title)
    : false;

export const ConfirmContext = createContext<ConfirmFn>(nativeConfirm);

/**
 * Hook impératif de confirmation : `if (await confirm({...})) { ... }`.
 *
 * Sous `<ConfirmProvider>` (cas de l'app) il ouvre le dialog stylé ; sinon il
 * retombe sur la confirmation native du navigateur.
 */
export function useConfirm(): ConfirmFn {
  return useContext(ConfirmContext);
}
