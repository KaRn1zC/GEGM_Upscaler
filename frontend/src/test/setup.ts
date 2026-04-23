import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
// Init i18next pour que les `t()` des composants résolvent les clés dans
// les tests au lieu d'afficher la clé brute (ex: "updater.available").
import i18n from "@/lib/i18n";

// Force la langue à `fr` sous jsdom — sinon `i18next-browser-languagedetector`
// pioche `en-US` depuis `navigator.language` par défaut de jsdom, et les
// assertions de test (écrites en FR) cassent. En prod le détecteur marche
// normalement (localStorage + navigator.language), c'est bien spécifique
// aux tests.
void i18n.changeLanguage("fr");

// ──────────────────────────────────────────────────────────────
// Polyfills jsdom — observers non fournis mais requis par Motion
// (whileInView, layout animations) et certains composants Radix.
// ──────────────────────────────────────────────────────────────

class IntersectionObserverMock implements IntersectionObserver {
  readonly root: Element | Document | null = null;
  readonly rootMargin: string = "";
  readonly scrollMargin: string = "";
  readonly thresholds: readonly number[] = [];

  constructor(
    _callback: IntersectionObserverCallback,
    _options?: IntersectionObserverInit,
  ) {}

  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

class ResizeObserverMock implements ResizeObserver {
  constructor(_callback: ResizeObserverCallback) {}
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

Object.defineProperty(globalThis, "IntersectionObserver", {
  value: IntersectionObserverMock,
  writable: true,
  configurable: true,
});

Object.defineProperty(globalThis, "ResizeObserver", {
  value: ResizeObserverMock,
  writable: true,
  configurable: true,
});

// matchMedia — requis par certaines features Motion (prefers-reduced-motion).
Object.defineProperty(globalThis, "matchMedia", {
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
  writable: true,
  configurable: true,
});

// Polyfill localStorage — Vitest 4 + jsdom 29 expose un objet vide
// sans les méthodes du Storage API, on le remplace par une Map interne.
class LocalStorageMock implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

Object.defineProperty(globalThis, "localStorage", {
  value: new LocalStorageMock(),
  writable: true,
  configurable: true,
});

// Réinitialise le stockage avant chaque test pour l'isolation.
beforeEach(() => {
  localStorage.clear();
});

// Nettoie le DOM après chaque test pour éviter les fuites entre suites.
afterEach(() => {
  cleanup();
});
