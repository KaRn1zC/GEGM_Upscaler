//! GEGM Upscaler — point d'entrée de l'application Tauri.
//!
//! Enregistre les plugins (dialog, fs, shell) et lance le runtime Tauri.
//! L'UI est servie par Vite en dev et depuis le bundle `dist/` en release.

mod commands;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            commands::get_system_resources,
        ])
        .setup(|_app| Ok(()))
        .run(tauri::generate_context!())
        .expect("erreur au lancement de l'application Tauri");
}
