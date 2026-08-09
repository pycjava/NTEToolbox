mod client_config;
mod debug_log;
mod maa_bridge;
mod mutopia_midi;
mod window_capture;
mod window_enumeration;

use debug_log::resolve_debug_log_dir;
use maa_bridge::{MaaBridgeRuntime, MaaTaskRunResponse, MaaTaskStartRequest, MaaTaskStatusUpdate};
use mutopia_midi::{DownloadedMidiEntry, MutopiaMidiEntry, MutopiaMidiDownloadRequest};
use serde_json::Value;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State};
use tauri_plugin_log::{RotationStrategy, Target, TargetKind};
use window_enumeration::WindowInfo;

// ── 实时视图推流 ────────────────────────────────────────────────────

const LIVE_VIEW_JPEG_QUALITY: u8 = 50;
const LIVE_VIEW_MAX_WIDTH: u32 = 512;
const LIVE_VIEW_MAX_HEIGHT: u32 = 480;
const LIVE_VIEW_LOG_EVERY_N_FRAMES: u64 = 30;
const CLIENT_LOG_FILE_NAME: &str = "ntetoolbox-client";
const CLIENT_LOG_MAX_FILE_SIZE: u128 = 20 * 1024 * 1024;
const CLIENT_LOG_KEEP_FILES: usize = 5;

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

        log::debug!("启动实时视图推流线程: target_window={target_window:?}, fps={fps}");

        let handle = thread::spawn(move || {
            let interval = Duration::from_millis(1000 / fps.max(1) as u64);
            let mut frame_index: u64 = 0;

            let mut capture_session =
                match window_capture::WindowCaptureSession::new(&target_window) {
                    Ok(session) => session,
                    Err(msg) => {
                        log::warn!("创建实时视图捕获会话失败: {msg}");
                        let _ = app.emit("live-view-error", msg);
                        return;
                    }
                };

            while !stop.load(Ordering::Relaxed) {
                let t0 = Instant::now();
                let log_details = frame_index % LIVE_VIEW_LOG_EVERY_N_FRAMES == 0;
                let capture_options = window_capture::CaptureOptions {
                    jpeg_quality: LIVE_VIEW_JPEG_QUALITY,
                    max_output_width: Some(LIVE_VIEW_MAX_WIDTH),
                    max_output_height: Some(LIVE_VIEW_MAX_HEIGHT),
                    log_details,
                };

                match capture_session.capture_jpeg(capture_options) {
                    Ok(frame) => {
                        let encode_b64_start = Instant::now();
                        let b64 = base64::Engine::encode(
                            &base64::engine::general_purpose::STANDARD,
                            &frame.jpeg_bytes,
                        );
                        let encode_b64 = encode_b64_start.elapsed();

                        let emit_start = Instant::now();
                        let _ = app.emit("live-view-frame", b64);
                        let emit_frame = emit_start.elapsed();

                        frame_index += 1;
                        if log_details {
                            log::debug!(
                                "推流帧 #{frame_index}: source={}x{}, output={}x{}, jpeg={} 字节, \
                                 total={:?}, capture={:?}, base64={:?}, emit={:?}",
                                frame.stats.source_width,
                                frame.stats.source_height,
                                frame.stats.output_width,
                                frame.stats.output_height,
                                frame.jpeg_bytes.len(),
                                t0.elapsed(),
                                frame.stats.timings.total,
                                encode_b64,
                                emit_frame
                            );
                        }
                    }
                    Err(msg) => {
                        log::warn!("截屏失败: {msg}");
                        let _ = app.emit("live-view-error", msg);
                    }
                }

                let elapsed = t0.elapsed();
                if elapsed < interval {
                    thread::sleep(interval - elapsed);
                }
            }

            log::debug!("实时视图推流线程退出: 共推送 {frame_index} 帧");
        });

        self.handle = Some(handle);
    }

    fn stop(&mut self) {
        self.stop_internal();
    }

    fn stop_internal(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(handle) = self.handle.take() {
            log::debug!("等待实时视图推流线程退出...");
            let _ = handle.join();
            log::debug!("实时视图推流线程已退出");
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
    log::debug!("start_live_view: target_window={target_window:?}, fps={fps}");
    state
        .lock()
        .map_err(|e| e.to_string())?
        .start(app, target_window, fps);
    Ok(())
}

#[tauri::command]
fn stop_live_view(state: State<'_, Mutex<LiveViewCapture>>) -> Result<(), String> {
    log::debug!("stop_live_view");
    state.lock().map_err(|e| e.to_string())?.stop();
    Ok(())
}

// ── 原有命令 ─────────────────────────────────────────────────────────

#[tauri::command]
fn load_client_config(app: AppHandle) -> Result<Option<Value>, String> {
    let config_dir = app
        .path()
        .app_config_dir()
        .map_err(|error| error.to_string())?;
    client_config::load_client_config_from_dir(&config_dir).map_err(|error| error.to_string())
}

#[tauri::command]
fn save_client_config(app: AppHandle, config: Value) -> Result<(), String> {
    let config_dir = app
        .path()
        .app_config_dir()
        .map_err(|error| error.to_string())?;
    client_config::save_client_config_to_dir(&config_dir, &config)
        .map_err(|error| error.to_string())
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

#[tauri::command]
fn poll_maa_task_states(
    runtime: State<'_, Mutex<MaaBridgeRuntime>>,
) -> Result<Vec<MaaTaskStatusUpdate>, String> {
    runtime
        .lock()
        .map_err(|error| error.to_string())?
        .poll_task_status_updates()
}

#[tauri::command]
async fn list_mutopia_public_domain_midi() -> Result<Vec<MutopiaMidiEntry>, String> {
    tauri::async_runtime::spawn_blocking(mutopia_midi::list_public_domain_piano_midi)
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn download_mutopia_midi(
    app: AppHandle,
    request: MutopiaMidiDownloadRequest,
) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || mutopia_midi::download_midi(&app, &request))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn list_downloaded_midi() -> Result<Vec<DownloadedMidiEntry>, String> {
    tauri::async_runtime::spawn_blocking(mutopia_midi::list_downloaded_midi)
        .await
        .map_err(|e| e.to_string())?
}

fn client_debug_log_dir(app: &tauri::App) -> Result<PathBuf, tauri::Error> {
    Ok(resolve_debug_log_dir(app.path().app_local_data_dir()?))
}

fn client_log_targets(debug_log_dir: PathBuf) -> Vec<Target> {
    let file_target = Target::new(TargetKind::Folder {
        path: debug_log_dir,
        file_name: Some(CLIENT_LOG_FILE_NAME.to_string()),
    });

    if cfg!(debug_assertions) {
        vec![Target::new(TargetKind::Stdout), file_target]
    } else {
        vec![file_target]
    }
}

fn stop_maa_runtime_on_exit(app: &AppHandle) {
    let runtime = app.state::<Mutex<MaaBridgeRuntime>>();
    match runtime.lock() {
        Ok(mut runtime) => {
            if let Err(error) = runtime.stop_all_tasks_with_reason("app_exit") {
                log::warn!("Failed to stop Maa runtime on app exit: {error}");
            }
        }
        Err(error) => {
            log::warn!("Failed to lock Maa runtime on app exit: {error}");
        }
    };
}

// ── 入口 ─────────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Mutex::new(MaaBridgeRuntime::default()))
        .manage(Mutex::new(LiveViewCapture::new()))
        .setup(|app| {
            let debug_log_dir = client_debug_log_dir(app)?;
            app.handle().plugin(
                tauri_plugin_log::Builder::default()
                    .clear_targets()
                    .targets(client_log_targets(debug_log_dir))
                    .rotation_strategy(RotationStrategy::KeepSome(CLIENT_LOG_KEEP_FILES))
                    .max_file_size(CLIENT_LOG_MAX_FILE_SIZE)
                    .level(log::LevelFilter::Info)
                    .level_for("ntetoolbox_client_lib", log::LevelFilter::Debug)
                    .build(),
            )?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            load_client_config,
            save_client_config,
            start_maa_task,
            stop_maa_task,
            poll_maa_task_states,
            list_mutopia_public_domain_midi,
            download_mutopia_midi,
            list_downloaded_midi,
            enumerate_windows,
            start_live_view,
            stop_live_view
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => stop_maa_runtime_on_exit(app),
            _ => {}
        });
}

#[cfg(test)]
mod mutopia_midi_tests {
    use crate::mutopia_midi::{
        parse_public_domain_midi_listing, validate_download_request, MutopiaMidiDownloadRequest,
    };

    #[test]
    fn parses_only_public_domain_midi_entries_from_mutopia_listing() {
        let html = r#"
        <table class="table-bordered result-table">
          <tr><td>Sonatine</td><td>by J. André (1741–1799)</td><td>Opus 34. I.</td><td>&nbsp;</td></tr>
          <tr><td>for Piano</td><td>18th Century</td><td>Classical</td><td></td></tr>
          <tr><td>Unknown</td><td><a href="../legal.html#publicdomain">Public Domain</a></td><td><a href="piece-info.cgi?id=207">More Information</a></td><td>2013/01/06</td></tr>
          <tr><td>Download: <a href="https://www.mutopiaproject.org/ftp/AndreJ/O34/andre-sonatine/andre-sonatine.ly">.ly file</a></td>
          <td><a href="https://www.mutopiaproject.org/ftp/AndreJ/O34/andre-sonatine/andre-sonatine.mid">.mid file</a></td></tr>
        </table>
        <table class="table-bordered result-table">
          <tr><td>Toccatina</td><td>by C.-V. Alkan (1813–1888)</td><td>Op.75</td><td>&nbsp;</td></tr>
          <tr><td>for Piano</td><td>1872</td><td>Romantic</td><td></td></tr>
          <tr><td>Paris</td><td><a href="../legal.html#ccasa">Creative Commons Attribution-ShareAlike 4.0</a></td><td><a href="piece-info.cgi?id=2163">More Information</a></td><td>2017/01/17</td></tr>
          <tr><td><a href="https://www.mutopiaproject.org/ftp/AlkanCV/O75/toccatina/toccatina.mid">.mid file</a></td></tr>
        </table>
        "#;

        let entries = parse_public_domain_midi_listing(html);

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].title, "Sonatine");
        assert_eq!(entries[0].composer, "J. André");
        assert_eq!(entries[0].instrument, "Piano");
        assert_eq!(entries[0].style, "Classical");
        assert_eq!(entries[0].license, "Public Domain");
        assert_eq!(
            entries[0].midi_url,
            "https://www.mutopiaproject.org/ftp/AndreJ/O34/andre-sonatine/andre-sonatine.mid"
        );
        assert_eq!(
            entries[0].source_url,
            "https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=207"
        );
    }

    #[test]
    fn rejects_download_requests_outside_mutopia_public_domain_midi() {
        let mut request = MutopiaMidiDownloadRequest {
            title: "Sonatine".to_string(),
            composer: "J. André".to_string(),
            license: "Creative Commons Attribution-ShareAlike 4.0".to_string(),
            midi_url: "https://www.mutopiaproject.org/ftp/AndreJ/O34/andre-sonatine/andre-sonatine.mid".to_string(),
        };

        assert!(validate_download_request(&request).is_err());

        request.license = "Public Domain".to_string();
        request.midi_url = "https://example.com/andre-sonatine.mid".to_string();
        assert!(validate_download_request(&request).is_err());

        request.midi_url = "https://www.mutopiaproject.org/ftp/AndreJ/O34/andre-sonatine/andre-sonatine.pdf".to_string();
        assert!(validate_download_request(&request).is_err());

        request.midi_url = "https://www.mutopiaproject.org/ftp/AndreJ/O34/andre-sonatine/andre-sonatine.mid".to_string();
        assert!(validate_download_request(&request).is_ok());
    }
}
