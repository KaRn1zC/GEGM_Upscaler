import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

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
