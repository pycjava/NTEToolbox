use serde_json::Value;
use std::{fs, io, path::Path};

pub fn load_client_config_from_dir(config_dir: &Path) -> io::Result<Option<Value>> {
  let config_path = config_dir.join("client-config.json");
  if !config_path.is_file() {
    return Ok(None);
  }

  let config_text = fs::read_to_string(config_path)?;
  let config = serde_json::from_str(&config_text)
    .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;

  Ok(Some(config))
}

pub fn save_client_config_to_dir(config_dir: &Path, config: &Value) -> io::Result<()> {
  fs::create_dir_all(config_dir)?;
  let config_text = serde_json::to_string_pretty(config)
    .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;

  fs::write(config_dir.join("client-config.json"), config_text)
}

#[cfg(test)]
mod tests {
  use super::*;
  use serde_json::json;

  #[test]
  fn saves_and_loads_client_config_json() {
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let config = json!({
      "version": 1,
      "games": {
        "nte": {
          "features": {
            "fish": {
              "optionValues": { "买饵次数": "9" },
              "pipelineOverride": { "钓鱼": { "attach": { "买饵次数": 9 } } }
            }
          }
        }
      }
    });

    save_client_config_to_dir(temp_dir.path(), &config).expect("save config");

    assert_eq!(load_client_config_from_dir(temp_dir.path()).expect("load config"), Some(config));
  }

  #[test]
  fn returns_none_when_client_config_does_not_exist() {
    let temp_dir = tempfile::tempdir().expect("temp dir");

    assert_eq!(load_client_config_from_dir(temp_dir.path()).expect("load config"), None);
  }
}
