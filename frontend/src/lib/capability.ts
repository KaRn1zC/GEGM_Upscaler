/**
 * Logique de décision "local vs cloud" pour le pipeline d'upscaling.
 *
 * Lit un snapshot de ressources système (via Tauri `get_system_resources`)
 * et applique les critères stricts définis en Phase H.1-bis : **tous** les
 * critères doivent passer simultanément pour que le mode local soit
 * autorisé. Dès qu'**un seul** critère échoue, on bascule sur cloud.
 *
 * Philosophie "safe by default" : mieux vaut perdre 5 min de traitement
 * cloud qu'un freeze complet de la machine utilisateur.
 */

/** Snapshot des ressources retourné par la commande Tauri. */
export interface SystemResources {
  // Hardware
  is_apple_silicon: boolean;
  chip: string;
  total_ram_gb: number;
  macos_version: string | null;

  // Runtime
  available_ram_gb: number;
  used_ram_gb: number;
  swap_used_gb: number;
  cpu_load_1min: number;
  memory_pressure: "normal" | "warn" | "critical";
  heavy_processes: { name: string; ram_gb: number }[];

  // Batterie
  is_on_battery: boolean;
  battery_percent: number | null;
}

/** Résultat de l'évaluation des capacités. */
export interface CapabilityDecision {
  /** Le mode local est autorisé (tous les critères passent). */
  can_run_local: boolean;
  /** Liste des critères qui ont échoué (vide si can_run_local = true). */
  blockers: string[];
  /** Snapshot source, pour affichage détaillé. */
  snapshot: SystemResources;
}

// ── Seuils stricts (Phase H.1-bis) ──────────────────────────

/** RAM totale minimale pour envisager le mode local. */
const MIN_TOTAL_RAM_GB = 16;
/** Version macOS minimale (Sonoma 14.0+). */
const MIN_MACOS_VERSION = "14.0";
/** RAM disponible minimale au moment de l'upload. */
const MIN_AVAILABLE_RAM_GB = 10;
/** Swap toléré (au-delà = pression mémoire, fallback cloud). */
const MAX_SWAP_USED_GB = 1;
/** Load average 1min max (fraction, ex. 0.4 = 40 %). */
const MAX_CPU_LOAD_1MIN = 0.4;
/** Nombre max de processus consommant plus de 1 GB en parallèle. */
const MAX_HEAVY_PROCESSES = 3;
/** Niveau de batterie minimum sur batterie (débranché). */
const MIN_BATTERY_PERCENT_UNPLUGGED = 30;

/**
 * Compare deux versions semver-like (ex: "14.5" vs "14.0").
 *
 * Retourne un nombre négatif si `a < b`, positif si `a > b`, 0 si égal.
 * Comparaison lexicographique par partie numérique, ignore le suffixe.
 */
function compareVersions(a: string, b: string): number {
  const partsA = a.split(".").map((p) => parseInt(p, 10) || 0);
  const partsB = b.split(".").map((p) => parseInt(p, 10) || 0);
  const len = Math.max(partsA.length, partsB.length);
  for (let i = 0; i < len; i++) {
    const diff = (partsA[i] ?? 0) - (partsB[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

/**
 * Évalue si le traitement local est autorisé selon les critères stricts.
 *
 * Tous les critères doivent passer. Dès qu'un seul échoue, le mode cloud
 * est forcé et la raison est retournée dans `blockers` (user-friendly).
 */
export function canRunLocalStrict(snap: SystemResources): CapabilityDecision {
  const blockers: string[] = [];

  // ── Hardware baseline ─────────────────────────────────────
  if (!snap.is_apple_silicon) {
    blockers.push("Chip Intel (Apple Silicon requis)");
  }
  if (snap.total_ram_gb < MIN_TOTAL_RAM_GB) {
    blockers.push(
      `RAM totale ${snap.total_ram_gb.toFixed(0)} Go < ${MIN_TOTAL_RAM_GB} Go requis`,
    );
  }
  if (snap.macos_version) {
    if (compareVersions(snap.macos_version, MIN_MACOS_VERSION) < 0) {
      blockers.push(`macOS ${snap.macos_version} < ${MIN_MACOS_VERSION}`);
    }
  } else {
    blockers.push("Version macOS indéterminée");
  }

  // ── Runtime availability ──────────────────────────────────
  if (snap.available_ram_gb < MIN_AVAILABLE_RAM_GB) {
    blockers.push(
      `RAM disponible ${snap.available_ram_gb.toFixed(1)} Go < ${MIN_AVAILABLE_RAM_GB} Go requis`,
    );
  }
  if (snap.swap_used_gb >= MAX_SWAP_USED_GB) {
    blockers.push(
      `Swap actif ${snap.swap_used_gb.toFixed(1)} Go (pression mémoire)`,
    );
  }
  if (snap.cpu_load_1min > MAX_CPU_LOAD_1MIN) {
    blockers.push(
      `CPU chargé à ${(snap.cpu_load_1min * 100).toFixed(0)} %`,
    );
  }
  if (snap.memory_pressure !== "normal") {
    blockers.push(`Memory Pressure macOS : ${snap.memory_pressure}`);
  }

  // Applications lourdes
  const heavy = snap.heavy_processes.filter((p) => p.ram_gb > 1);
  if (heavy.length > MAX_HEAVY_PROCESSES) {
    const names = heavy
      .slice(0, 3)
      .map((p) => p.name)
      .join(", ");
    blockers.push(
      `${heavy.length} applications lourdes actives (${names}…)`,
    );
  }

  // ── Batterie ──────────────────────────────────────────────
  if (snap.is_on_battery && snap.battery_percent !== null) {
    if (snap.battery_percent < MIN_BATTERY_PERCENT_UNPLUGGED) {
      blockers.push(
        `Batterie ${snap.battery_percent} % (< ${MIN_BATTERY_PERCENT_UNPLUGGED} % et débranché)`,
      );
    }
  }

  return {
    can_run_local: blockers.length === 0,
    blockers,
    snapshot: snap,
  };
}

/**
 * Formate un résumé court des ressources pour affichage UI.
 *
 * Ex: "M3 Pro · 12.5 / 18 Go dispo · swap 0.2 Go".
 */
export function formatResourcesSummary(snap: SystemResources): string {
  const chip = snap.chip.replace("Apple ", "");
  const ram = `${snap.available_ram_gb.toFixed(1)} / ${snap.total_ram_gb.toFixed(0)} Go dispo`;
  const swap =
    snap.swap_used_gb > 0.1
      ? `swap ${snap.swap_used_gb.toFixed(1)} Go`
      : "swap OK";
  return `${chip} · ${ram} · ${swap}`;
}
