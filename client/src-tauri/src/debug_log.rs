use std::fs::{self, OpenOptions};
use std::path::{Path, PathBuf};

pub fn resolve_debug_log_dir(app_local_data_dir: PathBuf) -> PathBuf {
    if let Ok(log_dir) = exe_debug_log_dir() {
        if is_log_dir_writable(&log_dir) {
            return log_dir;
        }
    }

    app_local_data_dir.join("maa-runtime").join("debug")
}

fn exe_debug_log_dir() -> Result<PathBuf, std::io::Error> {
    let exe_path = std::env::current_exe()?;
    let exe_dir = exe_path
        .parent()
        .map(|path| path.to_path_buf())
        .unwrap_or_else(|| PathBuf::from("."));
    Ok(exe_dir.join("debug"))
}

fn is_log_dir_writable(path: &Path) -> bool {
    if fs::create_dir_all(path).is_err() {
        return false;
    }

    let probe_path = path.join(".ntetoolbox-log-write-test");
    let writable = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&probe_path)
        .is_ok();
    let _ = fs::remove_file(probe_path);

    writable
}
