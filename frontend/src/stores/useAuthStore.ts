import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  AUTH_MODE,
  OIDC_CLIENT_ID,
  OIDC_ISSUER,
  refreshAccessToken,
  type TokenSet,
} from "@/lib/auth";

/**
 * Store Zustand pour l'état d'authentification (accessible hors React via
 * `useAuthStore.getState()` — consommé par `lib/api.ts` et `hooks/useUpload.ts`
 * pour récupérer le token courant au moment de chaque appel).
 *
 * Persistance : `localStorage` via middleware `persist`. Avantages :
 *   - l'utilisateur reste connecté après reload (pas de nouveau login à
 *     chaque F5)
 *   - multi-onglets sync (changement dans un onglet propagé aux autres)
 *
 * Risque XSS : un script malveillant injecté dans l'app pourrait lire le
 * token. Accepté pour un outil interne corporate — une vraie BFF pattern
 * (token httpOnly cookie côté backend) serait plus sûre mais overkill.
 *
 * En mode `dev` (AUTH_MODE=dev), le store expose simplement le
 * `VITE_DEV_TOKEN` et `isAuthenticated: true` constant — pas de flow
 * Keycloak, l'app démarre directement sur /upscale.
 */

interface AuthState {
  /** `null` tant que le user n'est pas loggé (mode oidc). */
  tokens: TokenSet | null;
  /** Flag de refresh en cours — évite les refreshs concurrents. */
  refreshing: boolean;

  setTokens: (tokens: TokenSet) => void;
  clearTokens: () => void;
  /**
   * Renvoie un access_token valide. Refresh si à <30s de l'expiration,
   * déclenche un logout + null si refresh échoue.
   */
  getValidToken: () => Promise<string | null>;
}

const DEV_STATIC_TOKEN =
  import.meta.env.VITE_DEV_TOKEN ?? "dev-secret-token-change-me";

const useAuthStoreBase = create<AuthState>()(
  persist(
    (set, get) => ({
      tokens: null,
      refreshing: false,

      setTokens: (tokens) => set({ tokens }),

      clearTokens: () => set({ tokens: null }),

      getValidToken: async () => {
        // Mode dev : pas de flow OIDC, on renvoie directement le token
        // statique. La persistance dans localStorage n'est pas nécessaire,
        // mais on fait ça pour que le comportement de `tokens` soit
        // cohérent entre modes.
        if (AUTH_MODE === "dev") {
          return DEV_STATIC_TOKEN;
        }

        const state = get();
        if (!state.tokens) return null;

        // Marge de sécurité 30s — refresh avant expiration réelle pour
        // éviter qu'un appel API parte avec un token qui expire pendant
        // la requête.
        const safetyMarginMs = 30_000;
        const isValid = state.tokens.expiresAt > Date.now() + safetyMarginMs;
        if (isValid) return state.tokens.accessToken;

        // Token expiré ou expire bientôt : refresh.
        if (!state.tokens.refreshToken) {
          set({ tokens: null });
          return null;
        }

        if (state.refreshing) {
          // Un refresh est déjà en cours — on attend qu'il finisse puis
          // on renvoie le token actuel (qui sera le nouveau après le set).
          await waitForRefresh(useAuthStoreBase);
          return get().tokens?.accessToken ?? null;
        }

        set({ refreshing: true });
        try {
          const fresh = await refreshAccessToken({
            issuer: OIDC_ISSUER,
            clientId: OIDC_CLIENT_ID,
            refreshToken: state.tokens.refreshToken,
          });
          set({ tokens: fresh, refreshing: false });
          return fresh.accessToken;
        } catch (err) {
          console.error("[useAuthStore] Refresh failed:", err);
          set({ tokens: null, refreshing: false });
          return null;
        }
      },
    }),
    {
      name: "gegm-upscaler-auth",
      storage: createJSONStorage(() => localStorage),
      // Ne persiste pas le flag transitoire `refreshing`.
      partialize: (state) => ({ tokens: state.tokens }),
    },
  ),
);

/** Polling léger pour attendre la fin d'un refresh en cours. */
async function waitForRefresh(
  store: typeof useAuthStoreBase,
  timeoutMs = 5000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (store.getState().refreshing && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 50));
  }
}

export const useAuthStore = useAuthStoreBase;

/**
 * Helper synchrone pour récupérer le token courant sans passer par le
 * hook React — utilisé par `buildAuthedUrl` et autres contextes hors
 * composant. Ne refresh PAS automatiquement — pour ça, utiliser
 * `useAuthStore.getState().getValidToken()`.
 */
export function getCurrentAccessToken(): string {
  if (AUTH_MODE === "dev") return DEV_STATIC_TOKEN;
  return useAuthStore.getState().tokens?.accessToken ?? "";
}
