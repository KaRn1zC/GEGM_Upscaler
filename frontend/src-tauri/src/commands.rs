//! Commandes Tauri exposées au frontend via `invoke()`.
//!
//! La commande principale est `get_system_resources` : elle remonte
//! l'état matériel et les métriques runtime de la machine utilisée
//! pour que le frontend puisse décider (logique `canRunLocalStrict`)
//! si l'upscale peut se faire en local (Core ML) ou doit aller sur
//! RunPod Serverless.

use serde::Serialize;
use sysinfo::{CpuRefreshKind, MemoryRefreshKind, ProcessRefreshKind, RefreshKind, System};

/// Snapshot des ressources système à un instant T.
///
/// Les valeurs de RAM sont en giga-octets décimaux (1 GB = 10^9 octets)
/// pour rester cohérent avec l'affichage Apple (1 GB dans "À propos de
/// ce Mac" = 10^9 octets, pas 2^30).
#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct SystemResources {
    // ── Hardware (stable pendant la session) ────────────────
    /// Vrai si le chip est Apple Silicon (M1, M2, M3, M4, etc.).
    pub is_apple_silicon: bool,
    /// Nom du chip (ex: "Apple M3 Pro", "Intel Xeon", etc.).
    pub chip: String,
    /// RAM totale installée, en GB décimaux.
    pub total_ram_gb: f64,
    /// Version de macOS (ex: "14.5", "15.1"). `None` sur d'autres OS.
    pub macos_version: Option<String>,

    // ── Runtime (variable, à rafraîchir fréquemment) ────────
    /// RAM disponible (libre + réutilisable rapidement par le kernel).
    /// Équivalent Activity Monitor "Memory Available".
    pub available_ram_gb: f64,
    /// RAM utilisée par des processus actifs, hors cache évictable.
    pub used_ram_gb: f64,
    /// Swap actuellement utilisé, en GB. Seuil critique : > 1 GB.
    pub swap_used_gb: f64,
    /// Load average du CPU sur 1 minute (fraction, 1.0 = 1 core saturé).
    /// Sur un Mac 10 cores, 0.4 = 4 cores équivalent utilisés.
    pub cpu_load_1min: f64,
    /// État de la memory pressure macOS, calculée à partir des stats kernel.
    /// Valeurs : "normal", "warn", "critical".
    pub memory_pressure: String,
    /// Liste des processus utilisant plus de 1 GB de RAM (triés desc).
    pub heavy_processes: Vec<HeavyProcess>,

    // ── Batterie (laptops uniquement) ────────────────────────
    /// Vrai si la machine est actuellement sur batterie (débranchée).
    pub is_on_battery: bool,
    /// Niveau de batterie en pourcentage (0-100). `None` si desktop.
    pub battery_percent: Option<u8>,
}

/// Représente un processus consommant une quantité notable de RAM.
#[derive(Debug, Serialize)]
pub struct HeavyProcess {
    /// Nom exécutable du processus (ex: "Google Chrome Helper").
    pub name: String,
    /// RAM utilisée par ce processus en GB décimaux.
    pub ram_gb: f64,
}

/// Commande Tauri : retourne un snapshot complet des ressources système.
///
/// Appelée côté frontend via `invoke('get_system_resources')`. Le frontend
/// combine les valeurs retournées via `canRunLocalStrict()` pour décider
/// du routage GPU.
#[tauri::command]
pub fn get_system_resources() -> SystemResources {
    let mut sys = System::new_with_specifics(
        RefreshKind::new()
            .with_cpu(CpuRefreshKind::everything())
            .with_memory(MemoryRefreshKind::everything())
            .with_processes(ProcessRefreshKind::everything()),
    );
    // Deux rafraîchissements rapprochés sont nécessaires pour avoir des
    // valeurs CPU non nulles (sysinfo calcule par delta).
    sys.refresh_all();

    let chip = detect_chip(&sys);
    let is_apple_silicon = chip.to_ascii_lowercase().contains("apple");

    // Bytes -> GB décimaux (1 GB = 10^9 octets, convention Apple).
    let bytes_to_gb = |bytes: u64| -> f64 { bytes as f64 / 1_000_000_000.0 };

    let total_ram_gb = bytes_to_gb(sys.total_memory());
    let available_ram_gb = bytes_to_gb(sys.available_memory());
    let used_ram_gb = bytes_to_gb(sys.used_memory());
    let swap_used_gb = bytes_to_gb(sys.used_swap());

    // Load average (1 min). Sur macOS le `System::load_average()` retourne
    // la moyenne UNIX standard — comparable directement au nombre de cores.
    let cpu_load_1min = System::load_average().one;

    let memory_pressure = detect_memory_pressure();

    // Processus > 1 GB, top 10 max pour éviter un payload énorme.
    let mut heavy_processes: Vec<HeavyProcess> = sys
        .processes()
        .values()
        .filter_map(|p| {
            let ram_gb = bytes_to_gb(p.memory());
            if ram_gb > 1.0 {
                Some(HeavyProcess {
                    name: p.name().to_string_lossy().into_owned(),
                    ram_gb,
                })
            } else {
                None
            }
        })
        .collect();
    heavy_processes.sort_by(|a, b| b.ram_gb.partial_cmp(&a.ram_gb).unwrap_or(std::cmp::Ordering::Equal));
    heavy_processes.truncate(10);

    let (is_on_battery, battery_percent) = detect_battery();
    let macos_version = detect_macos_version();

    SystemResources {
        is_apple_silicon,
        chip,
        total_ram_gb,
        macos_version,
        available_ram_gb,
        used_ram_gb,
        swap_used_gb,
        cpu_load_1min,
        memory_pressure,
        heavy_processes,
        is_on_battery,
        battery_percent,
    }
}

/// Détecte le nom du chip via `System::cpus()` (première CPU).
fn detect_chip(sys: &System) -> String {
    sys.cpus()
        .first()
        .map(|c| c.brand().to_string())
        .unwrap_or_else(|| "Unknown".to_string())
}

/// Détecte la memory pressure via `vm_stat` (macOS) ou heuristique.
///
/// `vm_stat` expose des compteurs de compressed pages qui sont un bon
/// proxy de la pression mémoire. À défaut on retombe sur une heuristique
/// basée sur la RAM libre vs totale.
fn detect_memory_pressure() -> String {
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        // `memory_pressure` est un outil natif macOS qui donne l'état exact.
        if let Ok(output) = Command::new("memory_pressure").output() {
            let stdout = String::from_utf8_lossy(&output.stdout);
            // Le programme écrit "System-wide memory free percentage: NN%"
            // et "The system has XXX (YY%) of memory pressure".
            let lower = stdout.to_ascii_lowercase();
            if lower.contains("critical") {
                return "critical".to_string();
            }
            if lower.contains("warn") {
                return "warn".to_string();
            }
            if lower.contains("normal") {
                return "normal".to_string();
            }
        }
    }
    // Fallback heuristique : on dit "normal" par défaut. Le frontend
    // appliquera ses autres critères (RAM libre, swap) pour décider.
    "normal".to_string()
}

/// Récupère niveau batterie + état débranché via `pmset -g batt` (macOS).
///
/// Retourne `(false, None)` sur les machines sans batterie (Mac Studio,
/// Mac mini, Mac Pro) ou en cas d'erreur de parsing.
fn detect_battery() -> (bool, Option<u8>) {
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        if let Ok(output) = Command::new("pmset").args(["-g", "batt"]).output() {
            let stdout = String::from_utf8_lossy(&output.stdout);
            // Exemple : "... 87%; discharging; ..." ou "... 100%; charged; ...".
            let is_on_battery = stdout.contains("discharging");
            let battery_percent = stdout
                .split_whitespace()
                .find(|t| t.ends_with("%;"))
                .and_then(|t| t.trim_end_matches("%;").parse::<u8>().ok());
            return (is_on_battery, battery_percent);
        }
    }
    (false, None)
}

/// Récupère la version macOS via `sw_vers -productVersion`.
fn detect_macos_version() -> Option<String> {
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        if let Ok(output) = Command::new("sw_vers").arg("-productVersion").output() {
            let version = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !version.is_empty() {
                return Some(version);
            }
        }
    }
    None
}
