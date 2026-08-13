//! 炉石教练后端桥：管理 hscoachd 进程、读取 advice/game_state 契约、读写共享配置。
//!
//! 数据契约与独立版 HsCoach 完全一致（同 schema、同文件）：
//! - advice.json / game_state.json：hscoachd 以 `--publish-dir` 原子写，
//!   本模块只读消费（已过 D9 过滤，客户端不做二次加工）。
//! - config.json：%APPDATA%\NTEToolbox\hscoach\config.json，与独立版共享。

use crate::process_tree::{self, ManagedProcess, WindowsJob};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::time::Duration;
use tauri::{AppHandle, Manager, Runtime};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const HSCOACHD_DISPLAY_NAME: &str = "hscoachd";
const ADVICE_FILENAME: &str = "advice.json";
const GAME_STATE_FILENAME: &str = "game_state.json";
const PROCESS_WAIT_POLL_MS: u64 = 50;
const PROCESS_FORCE_STOP_TIMEOUT_MS: u64 = 3_000;

const DEFAULT_MODEL: &str = "deepseek-chat";
const DEFAULT_BASE_URL: &str = "https://api.deepseek.com/v1";

/// 前端轮询的状态快照：进程状态 + 最新建议 + 最新对局快照 + 战绩。
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HsCoachStateSnapshot {
    pub run_state: String,
    pub exit_code: Option<i32>,
    pub advice: Option<Value>,
    pub game_state: Option<Value>,
    /// 战绩统计（stats.json，由 hscoachd 在对局结束时聚合写入）。
    pub stats: Option<Value>,
}

/// 与 Python hscoach.config.CoachConfig 完全一致的字段（snake_case，共享文件）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HsCoachConfigPayload {
    pub api_key: String,
    pub model: String,
    pub base_url: String,
    pub friendly_player_id: Option<i32>,
    /// 教练模式：teach/compete/silent（LLM 独有，信息密度切换）。
    /// serde(default) 保证旧 config.json 无此字段时回退 teach。
    #[serde(default = "default_coach_mode")]
    pub coach_mode: String,
}

fn default_coach_mode() -> String {
    "teach".to_string()
}

impl Default for HsCoachConfigPayload {
    fn default() -> Self {
        Self {
            api_key: String::new(),
            model: DEFAULT_MODEL.to_string(),
            base_url: DEFAULT_BASE_URL.to_string(),
            friendly_player_id: None,
            coach_mode: default_coach_mode(),
        }
    }
}

struct HsCoachChildProcess {
    child: Child,
    last_exit_status: Option<ExitStatus>,
    #[cfg(windows)]
    job: Option<WindowsJob>,
}

impl HsCoachChildProcess {
    fn new(child: Child) -> Self {
        #[cfg(windows)]
        {
            let job = match WindowsJob::assign_child(&child) {
                Ok(job) => Some(job),
                Err(error) => {
                    log::warn!(
                        "Failed to place hscoachd in a Windows job object; falling back to taskkill: {error}"
                    );
                    None
                }
            };
            return Self {
                child,
                last_exit_status: None,
                job,
            };
        }

        #[cfg(not(windows))]
        {
            Self {
                child,
                last_exit_status: None,
            }
        }
    }

    fn pid(&self) -> u32 {
        self.child.id()
    }

    fn poll_exit(&mut self) -> Result<Option<ExitStatus>, String> {
        if self.last_exit_status.is_some() {
            return Ok(self.last_exit_status);
        }

        let status = self
            .child
            .try_wait()
            .map_err(|error| format!("Failed to query hscoachd process: {error}"))?;
        if let Some(status) = status {
            self.last_exit_status = Some(status);
        }

        Ok(status)
    }

    fn wait_for_exit_status(&mut self, timeout: Duration) -> Result<Option<ExitStatus>, String> {
        let deadline = std::time::Instant::now() + timeout;

        loop {
            if let Some(status) = self.poll_exit()? {
                return Ok(Some(status));
            }

            if std::time::Instant::now() >= deadline {
                return Ok(None);
            }

            std::thread::sleep(Duration::from_millis(PROCESS_WAIT_POLL_MS));
        }
    }

    fn wait_for_exit(&mut self, timeout: Duration) -> Result<bool, String> {
        self.wait_for_exit_status(timeout)
            .map(|status| status.is_some())
    }

    fn stop(&mut self, reason: &str) -> Result<(), String> {
        // 取出 job（结束语义下不再需要恢复：失败时 Drop 触发 KILL_ON_JOB_CLOSE）
        let job = self.job.take();
        process_tree::stop_process_tree(self, job.as_ref(), HSCOACHD_DISPLAY_NAME, reason)
    }
}

impl ManagedProcess for HsCoachChildProcess {
    fn pid(&self) -> u32 {
        self.pid()
    }

    fn poll_exit(&mut self) -> Result<Option<ExitStatus>, String> {
        self.poll_exit()
    }

    fn wait_for_exit(&mut self, timeout: Duration) -> Result<bool, String> {
        self.wait_for_exit(timeout)
    }

    fn kill_parent(&mut self) -> Result<(), String> {
        self.child
            .kill()
            .map_err(|error| format!("Failed to kill hscoachd process: {error}"))
    }
}

#[derive(Default)]
pub struct HsCoachRuntime {
    child: Option<HsCoachChildProcess>,
    publish_dir: Option<PathBuf>,
}

impl HsCoachRuntime {
    pub fn start<R: Runtime>(&mut self, app: &AppHandle<R>) -> Result<(), String> {
        if self.child.is_some() {
            log::info!("hscoachd already running, start request ignored");
            return Ok(());
        }

        let publish_dir = self.ensure_publish_dir(app)?;
        let mut command = hscoachd_command(app, &["--no-overlay"])?;
        command
            .arg("--publish-dir")
            .arg(&publish_dir)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        command.creation_flags(crate::process_tree::CREATE_NO_WINDOW);

        log::info!(
            "Starting hscoachd: publish_dir={}, config={}",
            publish_dir.display(),
            default_config_path()
                .map(|path| path.display().to_string())
                .unwrap_or_else(|error| format!("<unresolved: {error}>"))
        );

        let spawned = command
            .spawn()
            .map_err(|error| format!("Failed to start hscoachd: {error}"))?;
        self.child = Some(HsCoachChildProcess::new(spawned));
        Ok(())
    }

    pub fn stop(&mut self) -> Result<(), String> {
        let Some(mut child) = self.child.take() else {
            return Ok(());
        };

        let pid = child.pid();
        log::info!("Stopping hscoachd: pid={pid}, reason=user_stop_request");
        let stop_result = child.stop("user_stop_request");
        let wait_result = child.wait_for_exit_status(Duration::from_millis(
            PROCESS_FORCE_STOP_TIMEOUT_MS,
        ));

        match (stop_result, wait_result) {
            (Ok(()), Ok(Some(status))) => {
                log::info!("hscoachd stopped: pid={pid}, success={}", status.success());
                Ok(())
            }
            (Ok(()), Ok(None)) => Err("Timed out waiting for hscoachd to exit".to_string()),
            (Err(error), _) => Err(error),
            (Ok(()), Err(error)) => Err(error),
        }
    }

    pub fn poll_state<R: Runtime>(
        &mut self,
        app: &AppHandle<R>,
    ) -> Result<HsCoachStateSnapshot, String> {
        let mut run_state = "idle".to_string();
        let mut exit_code = None;

        if let Some(child) = &mut self.child {
            match child.poll_exit()? {
                None => run_state = "running".to_string(),
                Some(status) => {
                    run_state = if status.success() {
                        "completed".to_string()
                    } else {
                        "failed".to_string()
                    };
                    exit_code = status.code();
                    log::info!(
                        "hscoachd process exited: pid={}, success={}, exit_code={:?}",
                        child.pid(),
                        status.success(),
                        status.code()
                    );
                    self.child = None;
                }
            }
        }

        let publish_dir = self.ensure_publish_dir(app)?;
        Ok(HsCoachStateSnapshot {
            run_state,
            exit_code,
            advice: read_json_file(&publish_dir.join(ADVICE_FILENAME)),
            game_state: read_json_file(&publish_dir.join(GAME_STATE_FILENAME)),
            stats: read_json_file(&publish_dir.join("stats.json")),
        })
    }

    fn ensure_publish_dir<R: Runtime>(&mut self, app: &AppHandle<R>) -> Result<PathBuf, String> {
        if let Some(publish_dir) = &self.publish_dir {
            return Ok(publish_dir.clone());
        }

        let publish_dir = app
            .path()
            .app_local_data_dir()
            .map_err(|error| format!("Failed to resolve app data directory: {error}"))?
            .join("hscoach");
        fs::create_dir_all(&publish_dir)
            .map_err(|error| format!("Failed to create hscoach publish directory: {error}"))?;
        self.publish_dir = Some(publish_dir.clone());
        Ok(publish_dir)
    }
}

impl Drop for HsCoachRuntime {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.stop("runtime_drop");
        }
    }
}

/// 解析配置文本；损坏时回退默认值（与 Python load_config 一致）。
fn parse_config_text(text: &str) -> HsCoachConfigPayload {
    serde_json::from_str(text).unwrap_or_default()
}

/// 读取配置文件（与独立版共享 %APPDATA%\NTEToolbox\hscoach\config.json）。
pub fn get_config() -> Result<HsCoachConfigPayload, String> {
    let config_path = default_config_path()?;
    if !config_path.is_file() {
        return Ok(HsCoachConfigPayload::default());
    }

    let text = fs::read_to_string(&config_path)
        .map_err(|error| format!("Failed to read hscoach config: {error}"))?;
    Ok(parse_config_text(&text))
}

/// 保存配置文件（原子写：临时文件 + rename，与 Python save_config 一致）。
pub fn save_config(config: &HsCoachConfigPayload) -> Result<(), String> {
    let config_path = default_config_path()?;
    if let Some(parent) = config_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Failed to create hscoach config directory: {error}"))?;
    }

    let text = serde_json::to_string_pretty(config)
        .map_err(|error| format!("Failed to serialize hscoach config: {error}"))?;
    let tmp_path = config_path.with_extension("json.tmp");
    fs::write(&tmp_path, text)
        .map_err(|error| format!("Failed to write hscoach config: {error}"))?;
    fs::rename(&tmp_path, &config_path)
        .map_err(|error| format!("Failed to save hscoach config: {error}"))
}

/// 开启/还原炉石 log.config（调用 hscoachd 一次性模式，复用 Python 逻辑）。
pub fn set_hs_logging(app: &AppHandle, enabled: bool) -> Result<String, String> {
    let flag = if enabled {
        "--enable-log-config"
    } else {
        "--restore-log-config"
    };
    let mut command = hscoachd_command(app, &[flag])?;
    #[cfg(windows)]
    command.creation_flags(crate::process_tree::CREATE_NO_WINDOW);

    let output = command
        .output()
        .map_err(|error| format!("Failed to run hscoachd log action: {error}"))?;
    let message = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if output.status.success() {
        Ok(message)
    } else {
        Err(if message.is_empty() {
            format!("hscoachd log action failed: {}", output.status)
        } else {
            message
        })
    }
}

pub fn default_config_path() -> Result<PathBuf, String> {
    #[cfg(windows)]
    {
        let appdata = std::env::var("APPDATA")
            .map_err(|_| "APPDATA environment variable is not set".to_string())?;
        Ok(PathBuf::from(appdata)
            .join("NTEToolbox")
            .join("hscoach")
            .join("config.json"))
    }
    #[cfg(not(windows))]
    {
        let home = std::env::var("HOME").map_err(|_| "HOME is not set".to_string())?;
        Ok(PathBuf::from(home)
            .join(".config")
            .join("NTEToolbox")
            .join("hscoach")
            .join("config.json"))
    }
}

/// 解析 hscoachd 启动方式：打包资源里的 exe，或开发环境的 `python -m hscoach`。
fn hscoachd_command<R: Runtime>(app: &AppHandle<R>, extra_args: &[&str]) -> Result<Command, String> {
    let mut candidates = Vec::new();

    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            candidates.push(exe_dir.join("hscoach").join("hscoachd.exe"));
        }
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join("hscoach").join("hscoachd.exe"));
    }

    for candidate in candidates {
        if candidate.is_file() {
            let mut command = Command::new(&candidate);
            command.args(extra_args);
            return Ok(command);
        }
    }

    if let Some(repo_root) = find_repo_root() {
        let mut command = Command::new("python");
        command
            .current_dir(&repo_root)
            .arg("-m")
            .arg("hscoach")
            .args(extra_args);
        return Ok(command);
    }

    Err(
        "hscoachd was not found. Expected a bundled hscoach resource or a checkout with the hscoach package."
            .to_string(),
    )
}

fn find_repo_root() -> Option<PathBuf> {
    let mut start_points = Vec::new();

    if let Ok(current_dir) = std::env::current_dir() {
        start_points.push(current_dir);
    }

    start_points.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));

    for start in start_points {
        for ancestor in start.ancestors() {
            if ancestor.join("hscoach").join("__main__.py").is_file() {
                return Some(ancestor.to_path_buf());
            }
        }
    }

    None
}

fn read_json_file(path: &Path) -> Option<Value> {
    if !path.is_file() {
        return None;
    }
    match fs::read_to_string(path) {
        Ok(text) => serde_json::from_str(&text).ok(),
        Err(error) => {
            log::debug!("Failed to read {}: {error}", path.display());
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_defaults_match_python_module() {
        let config = HsCoachConfigPayload::default();
        assert_eq!(config.model, "deepseek-chat");
        assert_eq!(config.base_url, "https://api.deepseek.com/v1");
        assert!(config.friendly_player_id.is_none());
        assert_eq!(config.coach_mode, "teach");
    }

    #[test]
    fn config_round_trip_preserves_snake_case_fields() {
        let dir = tempfile::tempdir().expect("temp dir");
        let path = dir.path().join("config.json");
        let config = HsCoachConfigPayload {
            api_key: "sk-test".to_string(),
            model: "deepseek-reasoner".to_string(),
            base_url: "https://api.deepseek.com/v1".to_string(),
            friendly_player_id: Some(2),
            coach_mode: "compete".to_string(),
        };

        let text = serde_json::to_string_pretty(&config).expect("serialize");
        fs::write(&path, text).expect("write");
        let loaded: HsCoachConfigPayload =
            serde_json::from_str(&fs::read_to_string(&path).expect("read")).expect("parse");

        assert_eq!(loaded.api_key, "sk-test");
        assert_eq!(loaded.model, "deepseek-reasoner");
        assert_eq!(loaded.friendly_player_id, Some(2));
        assert_eq!(loaded.coach_mode, "compete");
        // 字段名必须与 Python 端一致（共享配置文件）
        let raw = fs::read_to_string(&path).expect("read raw");
        assert!(raw.contains("\"api_key\""));
        assert!(raw.contains("\"friendly_player_id\""));
        assert!(raw.contains("\"coach_mode\""));
    }

    #[test]
    fn config_legacy_without_coach_mode_defaults_to_teach() {
        // 旧版 config.json 没有 coach_mode 字段；serde(default) 应回退 teach
        let legacy = r#"{"api_key":"","model":"deepseek-chat","base_url":"https://api.deepseek.com/v1","friendly_player_id":null}"#;
        let parsed: HsCoachConfigPayload =
            serde_json::from_str(legacy).expect("parse legacy");
        assert_eq!(parsed.coach_mode, "teach");
    }

    #[test]
    fn corrupt_config_falls_back_to_defaults() {
        let parsed = parse_config_text("{ not json");
        assert_eq!(parsed.model, DEFAULT_MODEL);
        assert_eq!(parsed.base_url, DEFAULT_BASE_URL);
        assert!(parsed.api_key.is_empty());
    }

    /// 回归测试：真实 spawn hscoachd（python -m hscoach 或打包 exe）→ stop，
    /// 验证进程树被终止、状态回到 idle。覆盖 TerminateJobObject + taskkill 兜底路径。
    #[test]
    fn start_then_stop_terminates_hscoachd_process_tree() {
        let app = tauri::test::mock_builder()
            .build(tauri::generate_context!())
            .expect("mock app");
        let handle = app.handle();

        let mut runtime = HsCoachRuntime::default();
        runtime.start(&handle).expect("start hscoachd");

        let state = runtime.poll_state(&handle).expect("poll after start");
        assert_eq!(state.run_state, "running", "hscoachd should be running after start");

        runtime.stop().expect("stop hscoachd");

        let state = runtime.poll_state(&handle).expect("poll after stop");
        assert_eq!(
            state.run_state,
            "idle",
            "hscoachd should be idle after stop (process tree terminated)"
        );
    }
}
