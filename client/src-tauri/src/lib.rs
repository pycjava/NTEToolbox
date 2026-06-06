mod client_config;
mod maa_bridge;
mod window_capture;
mod window_enumeration;

use maa_bridge::{MaaBridgeRuntime, MaaTaskRunResponse, MaaTaskStartRequest};
use window_enumeration::WindowInfo;
use serde_json::Value;
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, State};

// ── 实时视图推流 ────────────────────────────────────────────────────

struct LiveViewCapture {
    stop: Arc<AtomicBool>,
    handle: Option<thread::JoinHandle<()>>,
}

impl LiveViewCapture {
    fn new() -> Self {
        LiveViewCapture {
            stop: Arc::new(AtomicBool::new(false)),
            handle: None,
        }
    }

    fn start(&mut self, app: AppHandle, target_window: String, fps: u32) {
        self.stop_internal();

        self.stop.store(false, Ordering::Relaxed);
        let stop = self.stop.clone();

        let handle = thread::spawn(move || {
            let interval = Duration::from_millis(1000 / fps.max(1) as u64);

            while !stop.load(Ordering::Relaxed) {
                let t0 = Instant::now();

                match window_capture::capture_window_jpeg(&target_window) {
                    Ok(jpeg_bytes) => {
                        let b64 = base64::Engine::encode(
                            &base64::engine::general_purpose::STANDARD,
                            &jpeg_bytes,
                        );
                        let _ = app.emit("live-view-frame", b64);
                    }
                    Err(msg) => {
                        let _ = app.emit("live-view-error", msg);
                    }
                }

                let elapsed = t0.elapsed();
                if elapsed < interval {
                    thread::sleep(interval - elapsed);
                }
            }
        });

        self.handle = Some(handle);
    }

    fn stop(&mut self) {
        self.stop_internal();
    }

    fn stop_internal(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

impl Drop for LiveViewCapture {
    fn drop(&mut self) {
        self.stop_internal();
    }
}

#[tauri::command]
fn start_live_view(
    app: AppHandle,
    state: State<'_, Mutex<LiveViewCapture>>,
    target_window: String,
    fps: u32,
) -> Result<(), String> {
    state
        .lock()
        .map_err(|e| e.to_string())?
        .start(app, target_window, fps);
    Ok(())
}

#[tauri::command]
fn stop_live_view(
    state: State<'_, Mutex<LiveViewCapture>>,
) -> Result<(), String> {
    state
        .lock()
        .map_err(|e| e.to_string())?
        .stop();
    Ok(())
}

// ── 原有命令 ─────────────────────────────────────────────────────────

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
fn enumerate_windows() -> Result<Vec<WindowInfo>, String> {
  window_enumeration::enumerate_visible_windows()
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

// ── 入口 ─────────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .manage(Mutex::new(MaaBridgeRuntime::default()))
    .manage(Mutex::new(LiveViewCapture::new()))
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
      stop_maa_task,
      enumerate_windows,
      start_live_view,
      stop_live_view
    ])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
