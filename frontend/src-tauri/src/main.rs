// Masque la console Windows en release (no-op sur macOS).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    gegm_upscaler_lib::run()
}
