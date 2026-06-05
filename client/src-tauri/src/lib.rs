mod client_config;

use serde_json::Value;
use tauri::{AppHandle, Manager};

#[tauri::command]
fn load_client_config(app: AppHandle) -> Result<Option<Value>, String> {
  let config_dir = app.path().app_config_dir().map_err(|error| error.to_string())?;
  client_config::load_client_config_from_dir(&config_dir).map_err(|error| error.to_string())
}

#[tauri::command]
fn save_client_config(app: AppHandle, config: Value) -> Result<(), String> {
  let config_dir = app.path().app_config_dir().map_err(|error| error.to_string())?;
  client_config::save_client_config_to_dir(&config_dir, &config).map_err(|error| error.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![load_client_config, save_client_config])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
