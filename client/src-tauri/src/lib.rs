mod client_config;
mod maa_bridge;

use maa_bridge::{MaaBridgeRuntime, MaaTaskRunResponse, MaaTaskStartRequest};
use serde_json::Value;
use std::sync::Mutex;
use tauri::State;
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

#[tauri::command]
fn start_maa_task(
  app: AppHandle,
  runtime: State<'_, Mutex<MaaBridgeRuntime>>,
  request: MaaTaskStartRequest,
) -> Result<MaaTaskRunResponse, String> {
  runtime
    .lock()
    .map_err(|error| error.to_string())?
    .start_task(&app, &request)
}

#[tauri::command]
fn stop_maa_task(
  runtime: State<'_, Mutex<MaaBridgeRuntime>>,
  game_id: String,
  feature_id: String,
) -> Result<MaaTaskRunResponse, String> {
  runtime
    .lock()
    .map_err(|error| error.to_string())?
    .stop_task(&game_id, &feature_id)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .manage(Mutex::new(MaaBridgeRuntime::default()))
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
    .invoke_handler(tauri::generate_handler![
      load_client_config,
      save_client_config,
      start_maa_task,
      stop_maa_task
    ])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
