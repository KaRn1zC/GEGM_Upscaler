import { useAuthStore } from "@/stores/useAuthStore";
import {
  AUTH_MODE,
  OIDC_CLIENT_ID,
  OIDC_ISSUER,
  buildAuthorizeUrl,
  buildLogoutUrl,
  generateCodeChallenge,
  generateCodeVerifier,
  generateState,
  getRedirectUri,
} from "@/lib/auth";

const STORAGE_VERIFIER = "gegm-upscaler-pkce-verifier";
const STORAGE_STATE = "gegm-upscaler-pkce-state";

/**
 * Hook de commodité qui expose l'état d'auth + les actions login/logout.
 *
 * En mode `dev`, `isAuthenticated` est toujours `true` (pas de flow de
 * connexion). En mode `oidc`, `isAuthenticated` devient `true` après un
 * callback réussi (échange code → tokens dans `useAuthStore`).
 */
export function useAuth() {
  const tokens = useAuthStore((s) => s.tokens);
  const clearTokens = useAuthStore((s) => s.clearTokens);

  const isAuthenticated = AUTH_MODE === "dev" || tokens !== null;
  const user = tokens?.profile ?? null;

  /**
   * Démarre le flow OIDC : génère PKCE + state, stocke le verifier en
   * sessionStorage, redirige vers l'authorization endpoint Keycloak.
   */
  const login = async (): Promise<void> => {
    if (AUTH_MODE === "dev") return;
    const verifier = generateCodeVerifier();
    const challenge = await generateCodeChallenge(verifier);
    const state = generateState();
    // sessionStorage (pas localStorage) — scope par onglet, disparaît
    // après login ou fermeture.
    sessionStorage.setItem(STORAGE_VERIFIER, verifier);
    sessionStorage.setItem(STORAGE_STATE, state);
    window.location.assign(
      buildAuthorizeUrl({
        issuer: OIDC_ISSUER,
        clientId: OIDC_CLIENT_ID,
        redirectUri: getRedirectUri(),
        codeChallenge: challenge,
        state,
      }),
    );
  };

  /**
   * Logout local (clear tokens) + optionnellement redirect vers le
   * end_session_endpoint Keycloak qui invalide la session côté IdP.
   */
  const logout = (opts: { redirectToIdp?: boolean } = {}): void => {
    const idToken = tokens?.idToken;
    clearTokens();
    if (opts.redirectToIdp && idToken && AUTH_MODE === "oidc") {
      window.location.assign(
        buildLogoutUrl(OIDC_ISSUER, idToken, window.location.origin),
      );
    }
  };

  return {
    isAuthenticated,
    user,
    login,
    logout,
    authMode: AUTH_MODE,
  };
}

/** Helpers réutilisés par la page de callback. */
export const PKCE_STORAGE = {
  VERIFIER: STORAGE_VERIFIER,
  STATE: STORAGE_STATE,
};
