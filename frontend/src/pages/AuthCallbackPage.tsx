import { useEffect, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { m } from "motion/react";
import { AlertCircle, Loader2 } from "lucide-react";
import {
  AUTH_MODE,
  OIDC_CLIENT_ID,
  OIDC_ISSUER,
  exchangeCodeForTokens,
  getRedirectUri,
} from "@/lib/auth";
import { PKCE_STORAGE } from "@/hooks/useAuth";
import { useAuthStore } from "@/stores/useAuthStore";

/**
 * Landing page du redirect Keycloak — échange le `code` contre un token
 * set, stocke dans `useAuthStore`, redirige sur `/upscale`.
 *
 * Gère :
 *  - validation du `state` (protection CSRF)
 *  - récupération du `code_verifier` depuis sessionStorage
 *  - cleanup sessionStorage après usage (code_verifier est single-use)
 *  - affichage d'erreur si l'échange échoue (Keycloak down, code expiré,
 *    state mismatch, etc.)
 */
export function AuthCallbackPage() {
  const [params] = useSearchParams();
  const setTokens = useAuthStore((s) => s.setTokens);
  // Initial phase calculée à partir d'AUTH_MODE pour éviter un setState
  // dans un useEffect dès le premier render (React 19 warning).
  const [phase, setPhase] = useState<"exchanging" | "done" | "error">(
    AUTH_MODE === "dev" ? "done" : "exchanging",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    // En mode dev, pas d'échange — phase déjà initialisée à "done" →
    // le Navigate ci-dessous redirige sans action côté OIDC.
    if (AUTH_MODE === "dev") return;

    // Ce useEffect fait du vrai travail side-effect (lecture URL params,
    // appel réseau pour l'échange de code, écriture du store auth). Les
    // setState synchrones dans les branches de validation ci-dessous sont
    // légitimes : on ne peut pas toujours dériver un état initial car il
    // faut d'abord valider code + state + verifier sur des données
    // externes. Le lint React 19 `set-state-in-effect` est un false
    // positive ici — on désactive le check sur ce callback.
    /* eslint-disable react-hooks/set-state-in-effect --
       side-effect genuine, cf. commentaire ci-dessus */
    const code = params.get("code");
    const state = params.get("state");
    const error = params.get("error");

    if (error) {
      setErrorMessage(params.get("error_description") || error);
      setPhase("error");
      return;
    }

    if (!code) {
      setErrorMessage("Paramètre `code` manquant dans le callback.");
      setPhase("error");
      return;
    }

    const storedState = sessionStorage.getItem(PKCE_STORAGE.STATE);
    if (!state || state !== storedState) {
      setErrorMessage(
        "State PKCE invalide — possible tentative CSRF, connexion refusée.",
      );
      setPhase("error");
      return;
    }

    const verifier = sessionStorage.getItem(PKCE_STORAGE.VERIFIER);
    if (!verifier) {
      setErrorMessage(
        "`code_verifier` PKCE manquant — session probablement expirée, réessaye depuis la page login.",
      );
      setPhase("error");
      return;
    }

    // Cleanup sessionStorage dès maintenant — le verifier est single-use,
    // qu'il réussisse ou échoue.
    sessionStorage.removeItem(PKCE_STORAGE.VERIFIER);
    sessionStorage.removeItem(PKCE_STORAGE.STATE);

    void exchangeCodeForTokens({
      issuer: OIDC_ISSUER,
      clientId: OIDC_CLIENT_ID,
      code,
      codeVerifier: verifier,
      redirectUri: getRedirectUri(),
    })
      .then((tokens) => {
        setTokens(tokens);
        setPhase("done");
      })
      .catch((err) => {
        setErrorMessage(err instanceof Error ? err.message : String(err));
        setPhase("error");
      });
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [params, setTokens]);

  if (phase === "done") {
    return <Navigate to="/upscale" replace />;
  }

  return (
    <div className="relative flex-1 min-h-screen flex items-center justify-center overflow-hidden bg-background">
      <div className="absolute inset-0 gradient-mesh opacity-40 pointer-events-none" />

      <m.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative z-10 w-full max-w-md px-8 py-12 text-center"
      >
        {phase === "exchanging" && (
          <>
            <Loader2 className="w-8 h-8 mx-auto text-primary animate-spin" strokeWidth={1.5} />
            <p className="mt-6 font-display font-light text-2xl text-foreground">
              Connexion en cours…
            </p>
            <p className="mt-3 text-sm text-muted-foreground">
              Échange du code d'autorisation avec Keycloak.
            </p>
          </>
        )}

        {phase === "error" && (
          <>
            <AlertCircle className="w-8 h-8 mx-auto text-destructive" strokeWidth={1.5} />
            <p className="mt-6 font-display font-light text-2xl text-foreground">
              Échec de la connexion
            </p>
            <p className="mt-3 text-sm text-destructive/80 font-mono break-words">
              {errorMessage}
            </p>
            <a
              href="/login"
              className="mt-8 inline-flex items-center gap-2 text-sm text-primary hover:text-primary/80 transition-colors"
            >
              ← Retour à la page de connexion
            </a>
          </>
        )}
      </m.div>
    </div>
  );
}
