//! 子进程生命周期管理底座：Windows Job Object + 优雅/强制停止。
//!
//! MaaPiCli（异环 agent）与 hscoachd（炉石教练）共用同一套进程树管理：
//! 进程放入 Job Object（KILL_ON_JOB_CLOSE，父进程退出即全树终止），
//! 停止时按 优雅（Job 终止）→ taskkill /T → 直接 kill 父进程 的顺序兜底。

use std::process::{Child, ExitStatus};
use std::time::Duration;

#[cfg(windows)]
use std::ffi::c_void;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
use std::{mem, os::windows::io::AsRawHandle, ptr};

#[cfg(windows)]
pub const CREATE_NO_WINDOW: u32 = 0x08000000;

#[cfg(windows)]
const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: u32 = 0x00002000;
#[cfg(windows)]
const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS: i32 = 9;
#[cfg(windows)]
const PROCESS_STOP_EXIT_CODE: u32 = 1;
const PROCESS_WAIT_POLL_MS: u64 = 50;
const PROCESS_GRACEFUL_STOP_TIMEOUT_MS: u64 = 1_500;
const PROCESS_FORCE_STOP_TIMEOUT_MS: u64 = 3_000;

/// 被托管的子进程抽象：停止逻辑只依赖这几个方法，具体包装类实现。
pub trait ManagedProcess {
    fn pid(&self) -> u32;
    fn poll_exit(&mut self) -> Result<Option<ExitStatus>, String>;
    fn wait_for_exit(&mut self, timeout: Duration) -> Result<bool, String>;
    /// 兜底：直接终止父进程（std Child::kill）。
    fn kill_parent(&mut self) -> Result<(), String>;
}

/// 非 Windows 平台上的占位类型，保持 stop_process_tree 签名一致。
#[cfg(not(windows))]
pub struct WindowsJob;

#[cfg(windows)]
type WindowsHandle = isize;

#[cfg(windows)]
#[repr(C)]
struct JobObjectBasicLimitInformation {
    per_process_user_time_limit: i64,
    per_job_user_time_limit: i64,
    limit_flags: u32,
    minimum_working_set_size: usize,
    maximum_working_set_size: usize,
    active_process_limit: u32,
    affinity: usize,
    priority_class: u32,
    scheduling_class: u32,
}

#[cfg(windows)]
#[repr(C)]
struct IoCounters {
    read_operation_count: u64,
    write_operation_count: u64,
    other_operation_count: u64,
    read_transfer_count: u64,
    write_transfer_count: u64,
    other_transfer_count: u64,
}

#[cfg(windows)]
#[repr(C)]
struct JobObjectExtendedLimitInformation {
    basic_limit_information: JobObjectBasicLimitInformation,
    io_info: IoCounters,
    process_memory_limit: usize,
    job_memory_limit: usize,
    peak_process_memory_used: usize,
    peak_job_memory_used: usize,
}

#[cfg(windows)]
#[link(name = "kernel32")]
extern "system" {
    fn CreateJobObjectW(attributes: *mut c_void, name: *const u16) -> WindowsHandle;
    fn SetInformationJobObject(
        job: WindowsHandle,
        info_class: i32,
        info: *mut c_void,
        info_length: u32,
    ) -> i32;
    fn AssignProcessToJobObject(job: WindowsHandle, process: WindowsHandle) -> i32;
    fn TerminateJobObject(job: WindowsHandle, exit_code: u32) -> i32;
    fn CloseHandle(handle: WindowsHandle) -> i32;
}

#[cfg(windows)]
pub struct WindowsJob {
    handle: WindowsHandle,
}

#[cfg(windows)]
impl WindowsJob {
    /// 创建 Job Object 并把子进程放入（KILL_ON_JOB_CLOSE）。
    /// 失败时返回错误信息，调用方回退到 taskkill 方案。
    pub fn assign_child(child: &Child) -> Result<Self, String> {
        let handle = unsafe { CreateJobObjectW(ptr::null_mut(), ptr::null()) };
        if handle == 0 {
            return Err(format!(
                "CreateJobObjectW failed: {}",
                std::io::Error::last_os_error()
            ));
        }

        let job = Self { handle };
        if let Err(error) = job.set_kill_on_close() {
            drop(job);
            return Err(error);
        }

        let process_handle = child.as_raw_handle() as WindowsHandle;
        if unsafe { AssignProcessToJobObject(job.handle, process_handle) } == 0 {
            let error = std::io::Error::last_os_error();
            drop(job);
            return Err(format!("AssignProcessToJobObject failed: {error}"));
        }

        Ok(job)
    }

    fn set_kill_on_close(&self) -> Result<(), String> {
        let mut info: JobObjectExtendedLimitInformation = unsafe { mem::zeroed() };
        info.basic_limit_information.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

        let ok = unsafe {
            SetInformationJobObject(
                self.handle,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                &mut info as *mut _ as *mut c_void,
                mem::size_of::<JobObjectExtendedLimitInformation>() as u32,
            )
        };
        if ok == 0 {
            Err(format!(
                "SetInformationJobObject failed: {}",
                std::io::Error::last_os_error()
            ))
        } else {
            Ok(())
        }
    }

    fn terminate(&self) -> Result<(), String> {
        let ok = unsafe { TerminateJobObject(self.handle, PROCESS_STOP_EXIT_CODE) };
        if ok == 0 {
            Err(format!(
                "TerminateJobObject failed: {}",
                std::io::Error::last_os_error()
            ))
        } else {
            Ok(())
        }
    }
}

#[cfg(windows)]
impl Drop for WindowsJob {
    fn drop(&mut self) {
        if unsafe { CloseHandle(self.handle) } == 0 {
            log::warn!(
                "Failed to close child process job object: {}",
                std::io::Error::last_os_error()
            );
        }
    }
}

/// 停止进程树：优雅（Job 终止）→ taskkill /T /F → 直接 kill 父进程。
/// display_name 用于日志（如 "MaaPiCli" / "hscoachd"）。
#[cfg(windows)]
pub fn stop_process_tree(
    process: &mut impl ManagedProcess,
    job: Option<&WindowsJob>,
    display_name: &str,
    reason: &str,
) -> Result<(), String> {
    let pid = process.pid();
    if process.poll_exit()?.is_some() {
        log::info!("{display_name} already exited before stop: pid={pid}, reason={reason}");
        return Ok(());
    }

    let mut errors = Vec::new();
    let job_terminate_result = job.map(WindowsJob::terminate);
    if let Some(result) = job_terminate_result {
        match result {
            Ok(()) => {
                log::info!(
                    "TerminateJobObject sent to {display_name} process tree: pid={pid}, reason={reason}, stop_exit_code={PROCESS_STOP_EXIT_CODE}"
                );
                if process
                    .wait_for_exit(Duration::from_millis(PROCESS_GRACEFUL_STOP_TIMEOUT_MS))?
                {
                    return Ok(());
                }
                errors.push(format!(
                    "Timed out waiting for {display_name} after TerminateJobObject"
                ));
            }
            Err(error) => errors.push(error),
        }
    }

    if process.poll_exit()?.is_some() {
        return Ok(());
    }

    match kill_windows_process_tree(pid, display_name) {
        Ok(()) => {
            log::info!("taskkill sent to {display_name} process tree: pid={pid}, reason={reason}");
            if process
                .wait_for_exit(Duration::from_millis(PROCESS_FORCE_STOP_TIMEOUT_MS))?
            {
                return Ok(());
            }
            errors.push(format!(
                "Timed out waiting for {display_name} after taskkill"
            ));
        }
        Err(error) => {
            if process.poll_exit()?.is_some() {
                return Ok(());
            }
            errors.push(error);
        }
    }

    if process.poll_exit()?.is_some() {
        return Ok(());
    }

    match process.kill_parent() {
        Ok(()) => {
            log::warn!("Fallback parent kill sent to {display_name}: pid={pid}, reason={reason}");
            if process.wait_for_exit(Duration::from_millis(PROCESS_FORCE_STOP_TIMEOUT_MS))? {
                errors.push("stopped only the parent process".to_string());
            } else {
                errors.push("fallback parent kill did not exit".to_string());
            }
        }
        Err(error) => {
            if process.poll_exit()?.is_some() {
                return Ok(());
            }
            errors.push(error);
        }
    }

    Err(format!(
        "Failed to stop {display_name} process tree: {}",
        errors.join("; ")
    ))
}

/// 非 Windows：直接 kill 父进程（无 Job Object / taskkill 依赖）。
#[cfg(not(windows))]
pub fn stop_process_tree(
    process: &mut impl ManagedProcess,
    _job: Option<&WindowsJob>,
    display_name: &str,
    reason: &str,
) -> Result<(), String> {
    let pid = process.pid();
    if process.poll_exit()?.is_none() {
        process
            .kill_parent()
            .map_err(|error| format!("Failed to stop {display_name} process: {error}"))?;
        log::info!("Kill sent to {display_name} process: pid={pid}, reason={reason}");

        if !process.wait_for_exit(Duration::from_millis(PROCESS_FORCE_STOP_TIMEOUT_MS))? {
            return Err(format!(
                "Timed out waiting for {display_name} to exit after kill"
            ));
        }
    } else {
        log::info!("{display_name} already exited before stop: pid={pid}, reason={reason}");
    }

    Ok(())
}

#[cfg(windows)]
fn kill_windows_process_tree(pid: u32, display_name: &str) -> Result<(), String> {
    let pid_arg = pid.to_string();
    let mut command = std::process::Command::new("taskkill");
    command
        .args(["/PID", pid_arg.as_str(), "/T", "/F"])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    command.creation_flags(CREATE_NO_WINDOW);

    let status = command.status().map_err(|error| {
        format!("Failed to run taskkill for {display_name} process tree: {error}")
    })?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("taskkill exited with status {status}"))
    }
}

// 供轮询 sleep 使用，与调用方解耦
#[allow(dead_code)]
pub fn wait_poll_interval() -> Duration {
    Duration::from_millis(PROCESS_WAIT_POLL_MS)
}
