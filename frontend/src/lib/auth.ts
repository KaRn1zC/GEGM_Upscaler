/**
 * Flow OIDC Authorization Code + PKCE pour Keycloak GEGM.
 *
 * Pourquoi PKCE et pas Implicit Flow : PKCE est le standard actuel pour
 * les SPAs, même sans backend-for-frontend. Il protège l'échange code →
 * token contre les attaques MITM même si le code est intercepté (l'attaquant
 * ne pourra pas l'échanger sans le `code_verifier` qui reste côté client).
 *
 * Pourquoi pas une lib (`oidc-client-ts`, `@react-keycloak/web`) : besoin
 * minimal (pas de iframe silent refresh, pas de multi-tab sync), code
 * maintenu en ~150 lignes, zero dépendance.
 *
 * Références :
 *  - RFC 7636 (PKCE) : https://datatracker.ietf.org/doc/html/rfc7636
 *  - OIDC 1.0 : https://openid.net/specs/openid-connect-core-1_0.html
 *  - Keycloak endpoints : https://www.keycloak.org/docs/latest/server_admin/
 */

/**
 * Mode d'authentification — détermine si le login passe par Keycloak OIDC
 * ou utilise un token statique de dev.
 *
 * - `dev` : `VITE_DEV_TOKEN` (fallback `dev-secret-token-change-me`)
 * - `oidc` : redirige vers `VITE_OIDC_ISSUER` et récupère un JWT
 */
export const AUTH_MODE = (import.meta.env.VITE_AUTH_MODE ?? "dev") as "dev" | "oidc";

export const OIDC_ISSUER = import.meta.env.VITE_OIDC_ISSUER ?? "";
export const OIDC_CLIENT_ID = import.meta.env.VITE_OIDC_CLIENT_ID ?? "gegm-upscaler";

/**
 * URI où Keycloak redirige après authentification. En dev/prod web, c'est
 * `{origin}/auth/callback`. En Tauri, pareil avec `origin = tauri://localhost`
 * ou `https://tauri.localhost` — Keycloak doit avoir cet URI whitelisté
 * dans la config du client OIDC.
 */
export function getRedirectUri(): string {
  const override = import.meta.env.VITE_OIDC_REDIRECT_URI;
  if (override) return override;
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/auth/callback`;
}

export interface TokenSet {
  accessToken: string;
  refreshToken?: string;
  idToken?: string;
  /** Timestamp Unix (ms) d'expiration du accessToken. */
  expiresAt: number;
  /** Profil utilisateur décodé depuis l'id_token (si présent). */
  profile?: {
    sub: string;
    email?: string;
    name?: string;
    preferred_username?: string;
  };
}

// ──────────────────────────────────────────────────────────────
// PKCE — génération cryptographique
// ──────────────────────────────────────────────────────────────

function base64UrlEncode(bytes: Uint8Array): string {
  let str = "";
  for (const b of bytes) str += String.fromCharCode(b);
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * Génère un `code_verifier` aléatoire (96 chars base64url, ~72 bytes
 * d'entropie — conforme RFC 7636 §4.1 qui exige 43-128 chars).
 */
export function generateCodeVerifier(): string {
  const bytes = new Uint8Array(72);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

/** SHA256 du verifier → challenge (méthode S256, RFC 7636 §4.2). */
export async function generateCodeChallenge(verifier: string): Promise<string> {
  const data = new TextEncoder().encode(verifier);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return base64UrlEncode(new Uint8Array(hash));
}

/** Random state pour protection CSRF pendant le redirect. */
export function generateState(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

// ──────────────────────────────────────────────────────────────
// Construction de l'URL d'authorization
// ──────────────────────────────────────────────────────────────

export function buildAuthorizeUrl(params: {
  issuer: string;
  clientId: string;
  redirectUri: string;
  codeChallenge: string;
  state: string;
}): string {
  const url = new URL(`${params.issuer}/protocol/openid-connect/auth`);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", params.clientId);
  url.searchParams.set("redirect_uri", params.redirectUri);
  url.searchParams.set("scope", "openid email profile");
  url.searchParams.set("code_challenge", params.codeChallenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("state", params.state);
  return url.toString();
}

// ──────────────────────────────────────────────────────────────
// Echange code → token
// ──────────────────────────────────────────────────────────────

interface TokenResponse {
  access_token: string;
  expires_in: number;
  refresh_token?: string;
  id_token?: string;
  token_type: "Bearer";
}

async function postToken(issuer: string, body: URLSearchParams): Promise<TokenSet> {
  const res = await fetch(`${issuer}/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`OIDC token endpoint failed (${res.status}): ${text}`);
  }
  const json = (await res.json()) as TokenResponse;
  const expiresAt = Date.now() + json.expires_in * 1000;
  return {
    accessToken: json.access_token,
    refreshToken: json.refresh_token,
    idToken: json.id_token,
    expiresAt,
    profile: json.id_token ? decodeIdToken(json.id_token) : undefined,
  };
}

export async function exchangeCodeForTokens(params: {
  issuer: string;
  clientId: string;
  code: string;
  codeVerifier: string;
  redirectUri: string;
}): Promise<TokenSet> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: params.clientId,
    code: params.code,
    redirect_uri: params.redirectUri,
    code_verifier: params.codeVerifier,
  });
  return postToken(params.issuer, body);
}

export async function refreshAccessToken(params: {
  issuer: string;
  clientId: string;
  refreshToken: string;
}): Promise<TokenSet> {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: params.clientId,
    refresh_token: params.refreshToken,
  });
  return postToken(params.issuer, body);
}

// ──────────────────────────────────────────────────────────────
// Décodage id_token (JWT) — pas de vérification de signature côté
// client, c'est le backend qui valide via JWKS. Ici on extrait juste
// les claims pour afficher le nom dans l'UI.
// ──────────────────────────────────────────────────────────────

function decodeIdToken(idToken: string): TokenSet["profile"] {
  try {
    const [, payload] = idToken.split(".");
    const padded = payload.replace(/-/g, "+").replace(/_/g, "/");
    const json = JSON.parse(atob(padded));
    return {
      sub: json.sub,
      email: json.email,
      name: json.name,
      preferred_username: json.preferred_username,
    };
  } catch {
    return undefined;
  }
}

// ──────────────────────────────────────────────────────────────
// Logout
// ──────────────────────────────────────────────────────────────

export function buildLogoutUrl(issuer: string, idToken: string, postLogoutRedirect: string): string {
  const url = new URL(`${issuer}/protocol/openid-connect/logout`);
  url.searchParams.set("id_token_hint", idToken);
  url.searchParams.set("post_logout_redirect_uri", postLogoutRedirect);
  return url.toString();
}
