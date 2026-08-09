use crate::debug_log::resolve_debug_log_dir;
use crate::process_tree::{self, ManagedProcess, WindowsJob};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
#[cfg(windows)]
use std::os::windows::fs::MetadataExt;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::{
    collections::HashMap,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    process::{Child, Command, ExitStatus, Stdio},
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Manager};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;
const MAA_PROCESS_WAIT_POLL_MS: u64 = 50;
const MAA_PROCESS_FORCE_STOP_TIMEOUT_MS: u64 = 3_000;
const FISH_SCREENSHOT_ROOT_ENV: &str = "NTE_TOOLBOX_INSTALL_ROOT";

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MaaTaskStartRequest {
    pub game_id: String,
    pub feature_id: String,
    pub task_name: String,
    pub controller_name: String,
    pub target_window: String,
    pub resource_name: String,
    pub option_keys: Vec<String>,
    pub option_values: HashMap<String, Value>,
    pub option_definitions: HashMap<String, MaaOptionDefinition>,
    pub global_option_key: String,
    pub global_settings_values: HashMap<String, Value>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum MaaOptionDefinition {
    Switch {
        key: String,
        #[serde(default, rename = "enabledOptionKeys")]
        enabled_option_keys: Vec<String>,
    },
    Select {
        key: String,
        #[serde(default, rename = "defaultValue")]
        default_value: String,
    },
    Input {
        key: String,
        inputs: Vec<MaaInputDefinition>,
    },
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaaInputDefinition {
    pub name: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaaTaskRunResponse {
    pub run_state: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaaTaskStatusUpdate {
    pub game_id: String,
    pub feature_id: String,
    pub run_state: String,
    pub exit_code: Option<i32>,
}

struct MaaChildProcess {
    child: Child,
    game_id: String,
    feature_id: String,
    last_exit_status: Option<ExitStatus>,
    #[cfg(windows)]
    job: Option<WindowsJob>,
}

impl MaaChildProcess {
    fn new(child: Child, game_id: String, feature_id: String) -> Self {
        #[cfg(windows)]
        {
            let job = match WindowsJob::assign_child(&child) {
                Ok(job) => Some(job),
                Err(error) => {
                    log::warn!(
                        "Failed to place MaaPiCli in a Windows job object; falling back to taskkill: {error}"
                    );
                    None
                }
            };
            return Self {
                child,
                game_id,
                feature_id,
                last_exit_status: None,
                job,
            };
        }

        #[cfg(not(windows))]
        {
            Self {
                child,
                game_id,
                feature_id,
                last_exit_status: None,
            }
        }
    }

    fn pid(&self) -> u32 {
        self.child.id()
    }

    fn send_run_command(&mut self) -> Result<(), String> {
        let pid = self.pid();
        if let Some(mut stdin) = self.child.stdin.take() {
            log::info!(
                "Sending MaaPiCli run command: pid={pid}, game_id={}, feature_id={}, command=RunTasks(6)",
                self.game_id,
                self.feature_id
            );
            stdin
                .write_all(b"6\n")
                .map_err(|error| format!("Failed to send MaaPiCli run command: {error}"))?;
            let _ = stdin.flush();
            log::info!(
                "MaaPiCli stdin closed after run command: pid={pid}, game_id={}, feature_id={}, close_reason=allow_clean_eof_exit_after_menu",
                self.game_id,
                self.feature_id
            );
        } else {
            log::warn!(
                "MaaPiCli stdin was already closed before run command: pid={pid}, game_id={}, feature_id={}",
                self.game_id,
                self.feature_id
            );
        }

        Ok(())
    }

    fn stop(&mut self, reason: &str) -> Result<(), String> {
        // 取出 job（结束语义下不再需要恢复：失败时 Drop 触发 KILL_ON_JOB_CLOSE）
        let job = self.job.take();
        process_tree::stop_process_tree(self, job.as_ref(), "MaaPiCli", reason)
    }

    fn poll_exit(&mut self) -> Result<Option<ExitStatus>, String> {
        if self.last_exit_status.is_some() {
            return Ok(self.last_exit_status);
        }

        let status = self
            .child
            .try_wait()
            .map_err(|error| format!("Failed to query MaaPiCli process: {error}"))?;
        if let Some(status) = status {
            self.last_exit_status = Some(status);
        }

        Ok(status)
    }

    fn wait_for_exit_status(&mut self, timeout: Duration) -> Result<Option<ExitStatus>, String> {
        let deadline = Instant::now() + timeout;

        loop {
            if let Some(status) = self.poll_exit()? {
                return Ok(Some(status));
            }

            if Instant::now() >= deadline {
                return Ok(None);
            }

            thread::sleep(Duration::from_millis(MAA_PROCESS_WAIT_POLL_MS));
        }
    }

    fn wait_for_exit(&mut self, timeout: Duration) -> Result<bool, String> {
        self.wait_for_exit_status(timeout)
            .map(|status| status.is_some())
    }
}

impl ManagedProcess for MaaChildProcess {
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
            .map_err(|error| format!("Failed to kill MaaPiCli process: {error}"))
    }
}

#[derive(Default)]
pub struct MaaBridgeRuntime {
    children: HashMap<String, MaaChildProcess>,
    runtime_root: Option<PathBuf>,
}

impl MaaBridgeRuntime {
    pub fn start_task(
        &mut self,
        app: &AppHandle,
        request: &MaaTaskStartRequest,
    ) -> Result<MaaTaskRunResponse, String> {
        let key = task_key(&request.game_id, &request.feature_id);
        self.stop_task_by_key(&key, "replace_existing_task_before_start")?;

        let runtime_root = self.ensure_runtime_root(app)?;
        let debug_log_dir = resolve_bridge_debug_log_dir(app)?;
        prepare_runtime_debug_dir(&runtime_root, &debug_log_dir)?;
        migrate_legacy_bridge_log_dir(&runtime_root, &debug_log_dir)?;

        write_maa_pi_config(&runtime_root, request)?;

        let stderr_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(debug_log_dir.join("maapicli_stderr.log"))
            .map_err(|error| format!("Failed to create MaaPiCli log file: {error}"))?;

        let mut command = Command::new(runtime_root.join("MaaPiCli.exe"));
        let install_root = resolve_install_root().unwrap_or_else(|error| {
            log::warn!(
                "Failed to resolve install root for fish screenshots, falling back to Maa runtime root: {error}"
            );
            runtime_root.clone()
        });
        command
            .current_dir(&runtime_root)
            .env(FISH_SCREENSHOT_ROOT_ENV, &install_root)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::from(stderr_file));

        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW);

        log::info!(
            "Starting MaaPiCli task: task_key={key}, game_id={}, feature_id={}, task_name={}, runtime_root={}, debug_log_dir={}, screenshot_root={}",
            request.game_id,
            request.feature_id,
            request.task_name,
            runtime_root.display(),
            debug_log_dir.display(),
            install_root.display()
        );
        let spawned_child = command
            .spawn()
            .map_err(|error| format!("Failed to start MaaPiCli: {error}"))?;
        let pid = spawned_child.id();
        let mut child = MaaChildProcess::new(
            spawned_child,
            request.game_id.clone(),
            request.feature_id.clone(),
        );
        log::info!(
            "MaaPiCli process started: task_key={key}, pid={pid}, game_id={}, feature_id={}",
            request.game_id,
            request.feature_id
        );

        // Take stdin ownership, write the "Run tasks" command, then drop to send EOF.
        // Dropping stdin closes the write end of the pipe so MaaPiCli sees EOF after
        // reading "6\n".  After the task finishes and MaaPiCli returns to its menu,
        // it reads EOF and exits cleanly instead of blocking forever on a pipe whose
        // write end is held in the HashMap.
        if let Err(error) = child.send_run_command() {
            let _ = child.stop("failed_to_send_run_command");
            let _ = child.wait_for_exit(Duration::from_millis(MAA_PROCESS_FORCE_STOP_TIMEOUT_MS));
            return Err(error);
            // stdin dropped here → MaaPiCli receives EOF
        }

        self.children.insert(key, child);

        Ok(MaaTaskRunResponse {
            run_state: "running".to_string(),
        })
    }

    pub fn stop_task(
        &mut self,
        game_id: &str,
        feature_id: &str,
    ) -> Result<MaaTaskRunResponse, String> {
        self.stop_task_by_key(&task_key(game_id, feature_id), "user_stop_request")?;

        Ok(MaaTaskRunResponse {
            run_state: "idle".to_string(),
        })
    }

    pub fn stop_all_tasks_with_reason(&mut self, reason: &str) -> Result<(), String> {
        let mut errors = Vec::new();
        let keys = self.children.keys().cloned().collect::<Vec<_>>();
        log::info!(
            "Stopping all MaaPiCli tasks: count={}, reason={reason}",
            keys.len()
        );

        for key in keys {
            if let Err(error) = self.stop_task_by_key(&key, reason) {
                errors.push(format!("{key}: {error}"));
            }
        }

        if errors.is_empty() {
            Ok(())
        } else {
            Err(format!("Failed to stop Maa tasks: {}", errors.join("; ")))
        }
    }

    pub fn poll_task_status_updates(&mut self) -> Result<Vec<MaaTaskStatusUpdate>, String> {
        let mut updates = Vec::new();

        for (key, child) in self.children.iter_mut() {
            let Some(exit_status) = child.poll_exit()? else {
                continue;
            };
            log::info!(
                "MaaPiCli process exited: task_key={key}, pid={}, game_id={}, feature_id={}, reason=process_exit, {}",
                child.pid(),
                child.game_id,
                child.feature_id,
                format_maa_exit_status(exit_status.success(), exit_status.code())
            );

            updates.push((
                key.clone(),
                MaaTaskStatusUpdate {
                    game_id: child.game_id.clone(),
                    feature_id: child.feature_id.clone(),
                    run_state: if exit_status.success() {
                        "completed".to_string()
                    } else {
                        "failed".to_string()
                    },
                    exit_code: exit_status.code(),
                },
            ));
        }

        for (key, _) in &updates {
            self.children.remove(key);
        }

        Ok(updates.into_iter().map(|(_, update)| update).collect())
    }

    fn stop_task_by_key(&mut self, key: &str, reason: &str) -> Result<(), String> {
        let Some(mut child) = self.children.remove(key) else {
            log::debug!(
                "MaaPiCli stop requested but task is not running: task_key={key}, reason={reason}"
            );
            return Ok(());
        };

        let pid = child.pid();
        log::info!(
            "Stopping MaaPiCli task: task_key={key}, pid={pid}, game_id={}, feature_id={}, reason={reason}",
            child.game_id,
            child.feature_id
        );
        let stop_result = child.stop(reason);
        let wait_result =
            child.wait_for_exit_status(Duration::from_millis(MAA_PROCESS_FORCE_STOP_TIMEOUT_MS));

        match (stop_result, wait_result) {
            (Ok(()), Ok(Some(exit_status))) => {
                log::info!(
                    "MaaPiCli task stopped: task_key={key}, pid={pid}, reason={reason}, {}",
                    format_maa_exit_status(exit_status.success(), exit_status.code())
                );
                Ok(())
            }
            (Ok(()), Ok(None)) => {
                log::warn!(
                    "Timed out waiting for MaaPiCli to exit after stop: task_key={key}, pid={pid}, reason={reason}"
                );
                Err("Timed out waiting for MaaPiCli to exit after stop".to_string())
            }
            (Ok(()), Err(error)) => Err(error),
            (Err(stop_error), Ok(Some(exit_status))) => {
                log::warn!(
                    "MaaPiCli stop reported an error after the process exited: task_key={key}, pid={pid}, reason={reason}, stop_error={stop_error}, {}",
                    format_maa_exit_status(exit_status.success(), exit_status.code())
                );
                Ok(())
            }
            (Err(stop_error), Ok(None)) => {
                log::warn!(
                    "MaaPiCli is still running after the stop timeout: task_key={key}, pid={pid}, reason={reason}, stop_error={stop_error}"
                );
                Err(format!(
                    "{stop_error}; MaaPiCli is still running after the stop timeout"
                ))
            }
            (Err(stop_error), Err(wait_error)) => Err(format!("{stop_error}; {wait_error}")),
        }
    }

    fn ensure_runtime_root(&mut self, app: &AppHandle) -> Result<PathBuf, String> {
        if let Some(runtime_root) = &self.runtime_root {
            if is_maa_runtime_root(runtime_root) {
                return Ok(runtime_root.clone());
            }
        }

        let runtime_root = ensure_maa_runtime_root(app)?;
        self.runtime_root = Some(runtime_root.clone());
        Ok(runtime_root)
    }
}

impl Drop for MaaBridgeRuntime {
    fn drop(&mut self) {
        if let Err(error) = self.stop_all_tasks_with_reason("runtime_drop") {
            log::warn!("Failed to stop Maa runtime during shutdown: {error}");
        }
    }
}


pub fn build_maa_pi_config(request: &MaaTaskStartRequest) -> Value {
    let mut win32 = Map::new();
    win32.insert("_placeholder".to_string(), json!(0));
    if let Some(window_id) = parse_window_id(&request.target_window) {
        win32.insert("window_id".to_string(), json!(window_id));
    }

    json!({
      "adb": {
        "adb_path": "",
        "address": "",
        "name": ""
      },
      "controller": {
        "name": request.controller_name
      },
      "controller_option": [],
      "gamepad": {
        "_placeholder": 0,
        "gamepad_type": ""
      },
      "global_option": build_global_options(request),
      "macos": {
        "input": "",
        "screencap": "",
        "title": "",
        "window_id": 0
      },
      "playcover": {
        "address": "",
        "uuid": ""
      },
      "resource": request.resource_name,
      "resource_option": [],
      "task": [
        {
          "name": request.task_name,
          "option": build_task_options(
            &request.option_keys,
            &request.option_values,
            &request.option_definitions
          )
        }
      ],
      "win32": Value::Object(win32),
      "wlroots": {
        "wlr_socket_path": ""
      }
    })
}

fn write_maa_pi_config(runtime_root: &Path, request: &MaaTaskStartRequest) -> Result<(), String> {
    let config_dir = runtime_root.join("config");
    fs::create_dir_all(&config_dir)
        .map_err(|error| format!("Failed to create Maa config directory: {error}"))?;

    let config = build_maa_pi_config(request);
    let config_text = serde_json::to_string_pretty(&config)
        .map_err(|error| format!("Failed to serialize Maa config: {error}"))?;

    fs::write(config_dir.join("maa_pi_config.json"), config_text)
        .map_err(|error| format!("Failed to write Maa config: {error}"))
}

fn ensure_maa_runtime_root(app: &AppHandle) -> Result<PathBuf, String> {
    let runtime_root = app
        .path()
        .app_local_data_dir()
        .map_err(|error| format!("Failed to resolve app data directory: {error}"))?
        .join("maa-runtime");

    for candidate in runtime_source_candidates(app) {
        if is_maa_runtime_root(&candidate) {
            prepare_runtime_root_from_source(&candidate, &runtime_root)?;
            return Ok(runtime_root);
        }
    }

    let Some(repo_root) = find_repo_root() else {
        if is_maa_runtime_root(&runtime_root) {
            return Ok(runtime_root);
        }

        return Err(
      "MaaFramework runtime was not found. Expected a bundled maafw resource or deps/bin in the repository."
        .to_string(),
    );
    };

    prepare_dev_runtime_root(&repo_root, &runtime_root)?;
    Ok(runtime_root)
}

fn resolve_bridge_debug_log_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let app_local_data_dir = app
        .path()
        .app_local_data_dir()
        .map_err(|error| format!("Failed to resolve app data directory: {error}"))?;
    Ok(resolve_debug_log_dir(app_local_data_dir))
}

fn prepare_runtime_debug_dir(runtime_root: &Path, shared_debug_dir: &Path) -> Result<(), String> {
    fs::create_dir_all(shared_debug_dir)
        .map_err(|error| format!("Failed to create shared debug directory: {error}"))?;

    let runtime_debug_dir = runtime_root.join("debug");
    if paths_point_to_same_location(&runtime_debug_dir, shared_debug_dir) {
        return Ok(());
    }

    if fs::symlink_metadata(&runtime_debug_dir).is_ok() {
        if paths_point_to_same_location(&runtime_debug_dir, shared_debug_dir) {
            return Ok(());
        }

        if is_link_like_dir(&runtime_debug_dir) {
            remove_link_like_dir(&runtime_debug_dir)?;
        } else {
            move_dir_contents(&runtime_debug_dir, shared_debug_dir)?;
            fs::remove_dir_all(&runtime_debug_dir).map_err(|error| {
                format!("Failed to remove runtime debug directory before redirecting logs: {error}")
            })?;
        }
    }

    create_debug_dir_redirect(&runtime_debug_dir, shared_debug_dir)
}

fn paths_point_to_same_location(left: &Path, right: &Path) -> bool {
    match (left.canonicalize(), right.canonicalize()) {
        (Ok(left), Ok(right)) => left == right,
        _ => left == right,
    }
}

#[cfg(windows)]
fn is_link_like_dir(path: &Path) -> bool {
    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
    fs::symlink_metadata(path)
        .map(|metadata| (metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT) != 0)
        .unwrap_or(false)
}

#[cfg(not(windows))]
fn is_link_like_dir(path: &Path) -> bool {
    fs::symlink_metadata(path)
        .map(|metadata| metadata.file_type().is_symlink())
        .unwrap_or(false)
}

fn remove_link_like_dir(path: &Path) -> Result<(), String> {
    fs::remove_dir(path)
        .or_else(|_| fs::remove_file(path))
        .map_err(|error| format!("Failed to remove existing runtime debug link: {error}"))
}

#[cfg(windows)]
fn create_debug_dir_redirect(link_path: &Path, target_path: &Path) -> Result<(), String> {
    if let Some(parent) = link_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Failed to create runtime debug parent directory: {error}"))?;
    }

    let mut command = Command::new("cmd");
    command
        .args(["/C", "mklink", "/J"])
        .arg(link_path)
        .arg(target_path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command.creation_flags(CREATE_NO_WINDOW);

    let status = command
        .status()
        .map_err(|error| format!("Failed to create runtime debug junction: {error}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!(
            "mklink failed while redirecting Maa logs: {status}"
        ))
    }
}

#[cfg(not(windows))]
fn create_debug_dir_redirect(link_path: &Path, target_path: &Path) -> Result<(), String> {
    if let Some(parent) = link_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Failed to create runtime debug parent directory: {error}"))?;
    }

    std::os::unix::fs::symlink(target_path, link_path)
        .map_err(|error| format!("Failed to create runtime debug symlink: {error}"))
}

fn move_dir_contents(source: &Path, target: &Path) -> Result<(), String> {
    fs::create_dir_all(target).map_err(|error| format!("Failed to create {target:?}: {error}"))?;

    for entry in
        fs::read_dir(source).map_err(|error| format!("Failed to read {source:?}: {error}"))?
    {
        let entry = entry.map_err(|error| format!("Failed to read directory entry: {error}"))?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());

        if source_path.is_dir() {
            move_dir_contents(&source_path, &target_path)?;
            fs::remove_dir_all(&source_path).map_err(|error| {
                format!("Failed to remove moved directory {source_path:?}: {error}")
            })?;
        } else {
            let target_path = available_target_path(&target_path);
            match fs::rename(&source_path, &target_path) {
                Ok(()) => {}
                Err(_) => {
                    fs::copy(&source_path, &target_path).map_err(|error| {
                        format!("Failed to copy {source_path:?} to {target_path:?}: {error}")
                    })?;
                    fs::remove_file(&source_path).map_err(|error| {
                        format!("Failed to remove moved file {source_path:?}: {error}")
                    })?;
                }
            }
        }
    }

    Ok(())
}

fn available_target_path(path: &Path) -> PathBuf {
    if !path.exists() {
        return path.to_path_buf();
    }

    let parent = path.parent().unwrap_or_else(|| Path::new(""));
    let stem = path
        .file_stem()
        .map(|stem| stem.to_string_lossy().to_string())
        .unwrap_or_else(|| "log".to_string());
    let extension = path
        .extension()
        .map(|extension| extension.to_string_lossy());

    for index in 1.. {
        let file_name = match &extension {
            Some(extension) => format!("{stem}-{index}.{extension}"),
            None => format!("{stem}-{index}"),
        };
        let candidate = parent.join(file_name);
        if !candidate.exists() {
            return candidate;
        }
    }

    unreachable!()
}

fn migrate_legacy_bridge_log_dir(
    runtime_root: &Path,
    shared_debug_dir: &Path,
) -> Result<(), String> {
    let legacy_log_dir = runtime_root.join("log");
    if !legacy_log_dir.is_dir() || paths_point_to_same_location(&legacy_log_dir, shared_debug_dir) {
        return Ok(());
    }

    move_dir_contents(&legacy_log_dir, shared_debug_dir)?;
    fs::remove_dir_all(&legacy_log_dir)
        .map_err(|error| format!("Failed to remove legacy bridge log directory: {error}"))
}

fn runtime_source_candidates(app: &AppHandle) -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            candidates.push(exe_dir.join("maafw"));
            candidates.push(exe_dir.to_path_buf());
        }
    }

    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join("maafw"));
        candidates.push(resource_dir.clone());
    }

    if let Ok(current_dir) = std::env::current_dir() {
        candidates.push(current_dir.join("maafw"));
        candidates.push(current_dir.clone());
    }

    candidates
}

fn is_maa_runtime_root(path: &Path) -> bool {
    path.join("MaaPiCli.exe").is_file()
        && path.join("interface.json").is_file()
        && path.join("resource").is_dir()
}

fn find_repo_root() -> Option<PathBuf> {
    let mut start_points = Vec::new();

    if let Ok(current_dir) = std::env::current_dir() {
        start_points.push(current_dir);
    }

    start_points.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));

    for start in start_points {
        for ancestor in start.ancestors() {
            if ancestor
                .join("deps")
                .join("bin")
                .join("MaaPiCli.exe")
                .is_file()
                && ancestor.join("assets").join("interface.jsonc").is_file()
                && ancestor.join("assets").join("resource").is_dir()
            {
                return Some(ancestor.to_path_buf());
            }
        }
    }

    None
}

fn prepare_runtime_root_from_source(source_root: &Path, runtime_root: &Path) -> Result<(), String> {
    fs::create_dir_all(runtime_root)
        .map_err(|error| format!("Failed to create Maa runtime directory: {error}"))?;

    copy_dir_contents(source_root, runtime_root)?;
    let has_packaged_agent = source_root.join("agent.exe").is_file();
    if !has_packaged_agent {
        let _ = fs::remove_file(runtime_root.join("agent.exe"));
    }
    write_runtime_interface(
        &runtime_root.join("interface.json"),
        &runtime_root.join("interface.json"),
        has_packaged_agent,
    )?;
    Ok(())
}

fn prepare_dev_runtime_root(repo_root: &Path, runtime_root: &Path) -> Result<(), String> {
    fs::create_dir_all(runtime_root)
        .map_err(|error| format!("Failed to create Maa runtime directory: {error}"))?;

    copy_dir_contents(&repo_root.join("deps").join("bin"), runtime_root)?;
    copy_dir_all(
        &repo_root.join("assets").join("resource"),
        &runtime_root.join("resource"),
    )?;

    let has_packaged_agent = repo_root.join("dist").join("agent.exe").is_file();
    if has_packaged_agent {
        fs::copy(
            repo_root.join("dist").join("agent.exe"),
            runtime_root.join("agent.exe"),
        )
        .map_err(|error| format!("Failed to copy agent.exe: {error}"))?;
    } else {
        let _ = fs::remove_file(runtime_root.join("agent.exe"));
        copy_dir_all(&repo_root.join("agent"), &runtime_root.join("agent"))?;
    }

    write_runtime_interface(
        &repo_root.join("assets").join("interface.jsonc"),
        &runtime_root.join("interface.json"),
        has_packaged_agent,
    )?;

    Ok(())
}

fn write_runtime_interface(
    source_interface: &Path,
    target_interface: &Path,
    use_packaged_agent: bool,
) -> Result<(), String> {
    let interface_text = fs::read_to_string(source_interface)
        .map_err(|error| format!("Failed to read interface.jsonc: {error}"))?;

    let mut interface_config: Value = serde_json::from_str(&strip_jsonc_comments(&interface_text))
        .map_err(|error| format!("Failed to parse interface.jsonc: {error}"))?;
    if use_packaged_agent {
        let Some(interface_object) = interface_config.as_object_mut() else {
            return Err("interface.json must contain a JSON object".to_string());
        };
        interface_object.insert(
            "agent".to_string(),
            json!({
              "child_exec": "./agent.exe",
              "child_args": []
            }),
        );
    }

    let interface_json = serde_json::to_string_pretty(&interface_config)
        .map_err(|error| format!("Failed to serialize interface.json: {error}"))?;
    fs::write(target_interface, interface_json)
        .map_err(|error| format!("Failed to write interface.json: {error}"))
}

fn strip_jsonc_comments(text: &str) -> String {
    let mut result = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    let mut in_string = false;
    let mut quote = '\0';
    let mut escaped = false;

    while let Some(ch) = chars.next() {
        if in_string {
            result.push(ch);
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == quote {
                in_string = false;
            }
            continue;
        }

        if ch == '"' || ch == '\'' {
            in_string = true;
            quote = ch;
            result.push(ch);
            continue;
        }

        if ch == '/' {
            match chars.peek().copied() {
                Some('/') => {
                    chars.next();
                    for next in chars.by_ref() {
                        if next == '\n' {
                            result.push('\n');
                            break;
                        }
                    }
                    continue;
                }
                Some('*') => {
                    chars.next();
                    let mut previous = '\0';
                    for next in chars.by_ref() {
                        if previous == '*' && next == '/' {
                            break;
                        }
                        previous = next;
                    }
                    continue;
                }
                _ => {}
            }
        }

        result.push(ch);
    }

    result
}

fn copy_dir_contents(source: &Path, target: &Path) -> Result<(), String> {
    fs::create_dir_all(target).map_err(|error| format!("Failed to create {target:?}: {error}"))?;

    for entry in
        fs::read_dir(source).map_err(|error| format!("Failed to read {source:?}: {error}"))?
    {
        let entry = entry.map_err(|error| format!("Failed to read directory entry: {error}"))?;
        let entry_path = entry.path();
        let target_path = target.join(entry.file_name());

        if entry_path.is_dir() {
            copy_dir_all(&entry_path, &target_path)?;
        } else {
            fs::copy(&entry_path, &target_path).map_err(|error| {
                format!("Failed to copy {entry_path:?} to {target_path:?}: {error}")
            })?;
        }
    }

    Ok(())
}

fn copy_dir_all(source: &Path, target: &Path) -> Result<(), String> {
    fs::create_dir_all(target).map_err(|error| format!("Failed to create {target:?}: {error}"))?;

    for entry in
        fs::read_dir(source).map_err(|error| format!("Failed to read {source:?}: {error}"))?
    {
        let entry = entry.map_err(|error| format!("Failed to read directory entry: {error}"))?;
        let entry_path = entry.path();
        let target_path = target.join(entry.file_name());

        if entry_path.is_dir() {
            copy_dir_all(&entry_path, &target_path)?;
        } else {
            fs::copy(&entry_path, &target_path).map_err(|error| {
                format!("Failed to copy {entry_path:?} to {target_path:?}: {error}")
            })?;
        }
    }

    Ok(())
}

fn task_key(game_id: &str, feature_id: &str) -> String {
    format!("{game_id}:{feature_id}")
}

fn format_maa_exit_status(success: bool, exit_code: Option<i32>) -> String {
    let exit_code = exit_code
        .map(|code| code.to_string())
        .unwrap_or_else(|| "<signal_or_unknown>".to_string());
    format!("success={success}, exit_code={exit_code}")
}

fn resolve_install_root() -> Result<PathBuf, String> {
    std::env::current_exe()
        .map(|path| install_root_from_exe_path(&path))
        .map_err(|error| format!("Failed to resolve current executable path: {error}"))
}

fn install_root_from_exe_path(exe_path: &Path) -> PathBuf {
    exe_path
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn build_global_options(request: &MaaTaskStartRequest) -> Vec<Value> {
    if request.global_option_key.is_empty() || request.global_settings_values.is_empty() {
        return Vec::new();
    }

    vec![json!({
      "inputs": stringify_value_map(&request.global_settings_values),
      "name": request.global_option_key,
      "value": "",
      "values": []
    })]
}

fn build_task_options(
    option_keys: &[String],
    option_values: &HashMap<String, Value>,
    option_definitions: &HashMap<String, MaaOptionDefinition>,
) -> Vec<Value> {
    log::debug!(
        "[maa_bridge] build_task_options: keys={option_keys:?}, def_keys={:?}",
        option_definitions.keys().collect::<Vec<_>>()
    );
    let mut options = Vec::new();
    let mut visited = Vec::new();

    for option_key in option_keys {
        append_option(
            option_key,
            option_values,
            option_definitions,
            &mut options,
            &mut visited,
        );
    }

    options
}

fn append_option(
    option_key: &str,
    option_values: &HashMap<String, Value>,
    option_definitions: &HashMap<String, MaaOptionDefinition>,
    options: &mut Vec<Value>,
    visited: &mut Vec<String>,
) {
    if visited.iter().any(|visited_key| visited_key == option_key) {
        return;
    }
    visited.push(option_key.to_string());

    let Some(option_definition) = option_definitions.get(option_key) else {
        log::debug!("[maa_bridge] append_option: '{option_key}' NOT in definitions, skipping");
        return;
    };

    match option_definition {
        MaaOptionDefinition::Switch {
            key,
            enabled_option_keys,
        } => {
            let enabled = option_values
                .get(key)
                .and_then(Value::as_bool)
                .unwrap_or(false);
            log::debug!(
                "[maa_bridge] append_option Switch: key='{key}', enabled={enabled}, children={enabled_option_keys:?}"
            );

            options.push(json!({
              "inputs": {},
              "name": key,
              "value": if enabled { "Yes" } else { "No" },
              "values": []
            }));

            if enabled {
                for child_key in enabled_option_keys {
                    append_option(
                        child_key,
                        option_values,
                        option_definitions,
                        options,
                        visited,
                    );
                }
            }
        }
        MaaOptionDefinition::Select { key, default_value } => {
            let value = option_values
                .get(key)
                .map(value_to_string)
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| default_value.clone());

            options.push(json!({
              "inputs": {},
              "name": key,
              "value": value,
              "values": []
            }));
        }
        MaaOptionDefinition::Input { key, inputs } => {
            let input_values = inputs
                .iter()
                .map(|input| {
                    (
                        input.name.clone(),
                        Value::String(
                            option_values
                                .get(&input.name)
                                .map(value_to_string)
                                .unwrap_or_default(),
                        ),
                    )
                })
                .collect::<Map<String, Value>>();

            options.push(json!({
              "inputs": input_values,
              "name": key,
              "value": "",
              "values": []
            }));
        }
    }
}

fn stringify_value_map(values: &HashMap<String, Value>) -> Map<String, Value> {
    values
        .iter()
        .map(|(key, value)| (key.clone(), Value::String(value_to_string(value))))
        .collect()
}

fn value_to_string(value: &Value) -> String {
    match value {
        Value::String(value) => value.clone(),
        Value::Bool(value) => value.to_string(),
        Value::Number(value) => value.to_string(),
        Value::Null => String::new(),
        other => other.to_string(),
    }
}

fn parse_window_id(target_window: &str) -> Option<u64> {
    let trimmed = target_window.trim();
    if trimmed.is_empty() {
        return None;
    }

    trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
        .and_then(|hex| u64::from_str_radix(hex, 16).ok())
        .or_else(|| trimmed.parse::<u64>().ok())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn replaces_runtime_debug_dir_with_shared_debug_link() {
        let temp = tempfile::tempdir().expect("tempdir");
        let runtime_root = temp.path().join("runtime");
        let shared_debug_dir = temp.path().join("install").join("debug");
        fs::create_dir_all(runtime_root.join("debug")).expect("runtime debug dir");
        fs::write(runtime_root.join("debug").join("old.log"), "old").expect("old log");

        prepare_runtime_debug_dir(&runtime_root, &shared_debug_dir).expect("prepare debug dir");
        fs::write(runtime_root.join("debug").join("probe.log"), "probe").expect("probe log");

        assert!(shared_debug_dir.join("old.log").is_file());
        assert!(shared_debug_dir.join("probe.log").is_file());
    }

    fn request() -> MaaTaskStartRequest {
        MaaTaskStartRequest {
            game_id: "nte".to_string(),
            feature_id: "fish".to_string(),
            task_name: "钓鱼".to_string(),
            controller_name: "Win PostMessage (默认)".to_string(),
            target_window: "12345".to_string(),
            resource_name: "默认".to_string(),
            option_keys: vec![
                "钓鱼终止时间开关".to_string(),
                "溜鱼设置".to_string(),
                "卖鱼买换饵开关".to_string(),
                "卖鱼买换饵设置".to_string(),
            ],
            option_values: HashMap::from([
                ("钓鱼终止时间开关".to_string(), json!(true)),
                ("钓鱼终止时长".to_string(), json!("4小时")),
                ("溜鱼_midpoint_pix_range".to_string(), json!("8")),
                ("溜鱼_midpoint_sleep_time".to_string(), json!("12")),
                ("卖鱼买换饵开关".to_string(), json!(false)),
                ("买饵次数".to_string(), json!("6")),
            ]),
            option_definitions: HashMap::from([
                (
                    "钓鱼终止时间开关".to_string(),
                    MaaOptionDefinition::Switch {
                        key: "钓鱼终止时间开关".to_string(),
                        enabled_option_keys: vec!["钓鱼终止时长".to_string()],
                    },
                ),
                (
                    "钓鱼终止时长".to_string(),
                    MaaOptionDefinition::Select {
                        key: "钓鱼终止时长".to_string(),
                        default_value: "2小时".to_string(),
                    },
                ),
                (
                    "溜鱼设置".to_string(),
                    MaaOptionDefinition::Input {
                        key: "溜鱼设置".to_string(),
                        inputs: vec![
                            MaaInputDefinition {
                                name: "溜鱼_midpoint_pix_range".to_string(),
                            },
                            MaaInputDefinition {
                                name: "溜鱼_midpoint_sleep_time".to_string(),
                            },
                        ],
                    },
                ),
                (
                    "卖鱼买换饵开关".to_string(),
                    MaaOptionDefinition::Switch {
                        key: "卖鱼买换饵开关".to_string(),
                        enabled_option_keys: vec![],
                    },
                ),
                (
                    "卖鱼买换饵设置".to_string(),
                    MaaOptionDefinition::Input {
                        key: "卖鱼买换饵设置".to_string(),
                        inputs: vec![MaaInputDefinition {
                            name: "买饵次数".to_string(),
                        }],
                    },
                ),
            ]),
            global_option_key: "全局设置".to_string(),
            global_settings_values: HashMap::from([
                ("debug_mode_switch".to_string(), json!("0")),
                ("logging_switch".to_string(), json!("1")),
            ]),
        }
    }

    #[test]
    fn deserializes_frontend_option_definition_field_names() {
        let request: MaaTaskStartRequest = serde_json::from_value(json!({
          "gameId": "nte",
          "featureId": "fish",
          "taskName": "fish",
          "controllerName": "Win PostMessage",
          "targetWindow": "12345",
          "resourceName": "Default",
          "optionKeys": ["stop"],
          "optionValues": {
            "stop": true,
            "duration": "4h"
          },
          "optionDefinitions": {
            "stop": {
              "type": "switch",
              "key": "stop",
              "enabledOptionKeys": ["duration"]
            },
            "duration": {
              "type": "select",
              "key": "duration",
              "defaultValue": "2h"
            }
          },
          "globalOptionKey": "",
          "globalSettingsValues": {}
        }))
        .expect("frontend request should deserialize");

        let MaaOptionDefinition::Switch {
            enabled_option_keys,
            ..
        } = request
            .option_definitions
            .get("stop")
            .expect("switch option")
        else {
            panic!("stop should deserialize as a switch option");
        };
        assert_eq!(enabled_option_keys, &vec!["duration".to_string()]);

        let MaaOptionDefinition::Select { default_value, .. } = request
            .option_definitions
            .get("duration")
            .expect("select option")
        else {
            panic!("duration should deserialize as a select option");
        };
        assert_eq!(default_value, "2h");

        let config = build_maa_pi_config(&request);
        assert_eq!(
            config["task"][0]["option"],
            json!([
              {
                "inputs": {},
                "name": "stop",
                "value": "Yes",
                "values": []
              },
              {
                "inputs": {},
                "name": "duration",
                "value": "4h",
                "values": []
              }
            ])
        );
    }

    #[test]
    fn builds_maa_pi_config_for_selected_task() {
        let config = build_maa_pi_config(&request());

        assert_eq!(config["controller"]["name"], "Win PostMessage (默认)");
        assert_eq!(config["resource"], "默认");
        assert_eq!(config["win32"]["window_id"], 12345);
        assert_eq!(config["global_option"][0]["name"], "全局设置");
        assert_eq!(
            config["global_option"][0]["inputs"]["debug_mode_switch"],
            "0"
        );
        assert_eq!(config["task"][0]["name"], "钓鱼");
        assert_eq!(
            config["task"][0]["option"],
            json!([
              {
                "inputs": {},
                "name": "钓鱼终止时间开关",
                "value": "Yes",
                "values": []
              },
              {
                "inputs": {},
                "name": "钓鱼终止时长",
                "value": "4小时",
                "values": []
              },
              {
                "inputs": {
                  "溜鱼_midpoint_pix_range": "8",
                  "溜鱼_midpoint_sleep_time": "12"
                },
                "name": "溜鱼设置",
                "value": "",
                "values": []
              },
              {
                "inputs": {},
                "name": "卖鱼买换饵开关",
                "value": "No",
                "values": []
              },
              {
                "inputs": {
                  "买饵次数": "6"
                },
                "name": "卖鱼买换饵设置",
                "value": "",
                "values": []
              }
            ])
        );
    }

    #[test]
    fn formats_maa_exit_status_for_lifecycle_logs() {
        assert_eq!(
            format_maa_exit_status(true, Some(0)),
            "success=true, exit_code=0"
        );
        assert_eq!(
            format_maa_exit_status(false, Some(1)),
            "success=false, exit_code=1"
        );
        assert_eq!(
            format_maa_exit_status(false, None),
            "success=false, exit_code=<signal_or_unknown>"
        );
    }

    #[test]
    fn resolves_install_root_from_executable_path() {
        assert_eq!(
            install_root_from_exe_path(Path::new("C:/Program Files/NTEToolbox/NTEToolbox.exe")),
            PathBuf::from("C:/Program Files/NTEToolbox")
        );
    }
}
