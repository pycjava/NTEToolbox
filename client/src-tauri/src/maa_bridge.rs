use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::{
  collections::HashMap,
  fs,
  io::Write,
  path::{Path, PathBuf},
  process::{Child, Command, Stdio},
};
use tauri::{AppHandle, Manager};

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

#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum MaaOptionDefinition {
  Switch {
    key: String,
    #[serde(default)]
    enabled_option_keys: Vec<String>,
  },
  Select {
    key: String,
    #[serde(default)]
    default_value: String,
  },
  Input {
    key: String,
    inputs: Vec<MaaInputDefinition>,
  },
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MaaInputDefinition {
  pub name: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaaTaskRunResponse {
  pub run_state: String,
}

#[derive(Default)]
pub struct MaaBridgeRuntime {
  children: HashMap<String, Child>,
  runtime_root: Option<PathBuf>,
}

impl MaaBridgeRuntime {
  pub fn start_task(
    &mut self,
    app: &AppHandle,
    request: &MaaTaskStartRequest,
  ) -> Result<MaaTaskRunResponse, String> {
    let key = task_key(&request.game_id, &request.feature_id);
    self.stop_task_by_key(&key)?;

    let runtime_root = self.ensure_runtime_root(app)?;
    write_maa_pi_config(&runtime_root, request)?;

    let mut child = Command::new(runtime_root.join("MaaPiCli.exe"))
      .current_dir(&runtime_root)
      .stdin(Stdio::piped())
      .stdout(Stdio::null())
      .stderr(Stdio::null())
      .spawn()
      .map_err(|error| format!("Failed to start MaaPiCli: {error}"))?;

    if let Some(stdin) = child.stdin.as_mut() {
      stdin
        .write_all(b"6\n")
        .map_err(|error| format!("Failed to send MaaPiCli run command: {error}"))?;
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
    self.stop_task_by_key(&task_key(game_id, feature_id))?;

    Ok(MaaTaskRunResponse {
      run_state: "idle".to_string(),
    })
  }

  fn stop_task_by_key(&mut self, key: &str) -> Result<(), String> {
    let Some(mut child) = self.children.remove(key) else {
      return Ok(());
    };

    if child
      .try_wait()
      .map_err(|error| format!("Failed to query MaaPiCli process: {error}"))?
      .is_none()
    {
      child
        .kill()
        .map_err(|error| format!("Failed to stop MaaPiCli process: {error}"))?;
    }

    let _ = child.wait();
    Ok(())
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
      if ancestor.join("deps").join("bin").join("MaaPiCli.exe").is_file()
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
  copy_dir_all(&repo_root.join("assets").join("resource"), &runtime_root.join("resource"))?;

  let has_packaged_agent = repo_root.join("dist").join("agent.exe").is_file();
  if has_packaged_agent {
    fs::copy(repo_root.join("dist").join("agent.exe"), runtime_root.join("agent.exe"))
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

  let mut interface_config: Value =
    serde_json::from_str(&strip_jsonc_comments(&interface_text))
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

  for entry in fs::read_dir(source).map_err(|error| format!("Failed to read {source:?}: {error}"))? {
    let entry = entry.map_err(|error| format!("Failed to read directory entry: {error}"))?;
    let entry_path = entry.path();
    let target_path = target.join(entry.file_name());

    if entry_path.is_dir() {
      copy_dir_all(&entry_path, &target_path)?;
    } else {
      fs::copy(&entry_path, &target_path)
        .map_err(|error| format!("Failed to copy {entry_path:?} to {target_path:?}: {error}"))?;
    }
  }

  Ok(())
}

fn copy_dir_all(source: &Path, target: &Path) -> Result<(), String> {
  fs::create_dir_all(target).map_err(|error| format!("Failed to create {target:?}: {error}"))?;

  for entry in fs::read_dir(source).map_err(|error| format!("Failed to read {source:?}: {error}"))? {
    let entry = entry.map_err(|error| format!("Failed to read directory entry: {error}"))?;
    let entry_path = entry.path();
    let target_path = target.join(entry.file_name());

    if entry_path.is_dir() {
      copy_dir_all(&entry_path, &target_path)?;
    } else {
      fs::copy(&entry_path, &target_path)
        .map_err(|error| format!("Failed to copy {entry_path:?} to {target_path:?}: {error}"))?;
    }
  }

  Ok(())
}

fn task_key(game_id: &str, feature_id: &str) -> String {
  format!("{game_id}:{feature_id}")
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
  fn builds_maa_pi_config_for_selected_task() {
    let config = build_maa_pi_config(&request());

    assert_eq!(config["controller"]["name"], "Win PostMessage (默认)");
    assert_eq!(config["resource"], "默认");
    assert_eq!(config["win32"]["window_id"], 12345);
    assert_eq!(config["global_option"][0]["name"], "全局设置");
    assert_eq!(config["global_option"][0]["inputs"]["debug_mode_switch"], "0");
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
}
