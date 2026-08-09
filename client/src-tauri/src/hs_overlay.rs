//! 炉石教练悬浮窗：透明、置顶、点击穿透、跟随炉石窗口。
//!
//! 悬浮窗是客户端的第二个 WebView 窗口（label "hs-overlay"），加载同一个
//! 前端构建产物；前端按 window.label 分支渲染精简的悬浮 UI。
//! 点击穿透用 Win32 WS_EX_LAYERED|WS_EX_TRANSPARENT 实现（Tauri 的
//! set_ignore_cursor_events 仅 macOS 可用）；窗口位置每 200ms 跟随目标窗口。

use raw_window_handle::{HasWindowHandle, RawWindowHandle};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Manager, PhysicalPosition, Position, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

const OVERLAY_LABEL: &str = "hs-overlay";
const OVERLAY_WIDTH: f64 = 380.0;
const OVERLAY_HEIGHT: f64 = 640.0;
const OVERLAY_MARGIN_RIGHT: i32 = 16;
const OVERLAY_OFFSET_TOP: i32 = 40;
const FOLLOW_POLL_MS: u64 = 200;

#[cfg(windows)]
const GWL_EXSTYLE: i32 = -20;
#[cfg(windows)]
const WS_EX_LAYERED: isize = 0x00080000;
#[cfg(windows)]
const WS_EX_TRANSPARENT: isize = 0x00000020;

#[cfg(windows)]
#[repr(C)]
struct Rect {
    left: i32,
    top: i32,
    right: i32,
    bottom: i32,
}

#[cfg(windows)]
#[link(name = "user32")]
extern "system" {
    fn GetWindowLongPtrW(hwnd: isize, index: i32) -> isize;
    fn SetWindowLongPtrW(hwnd: isize, index: i32, new_long: isize) -> isize;
    fn GetWindowRect(hwnd: isize, rect: *mut Rect) -> i32;
}

pub struct HsOverlayRuntime {
    stop: Arc<AtomicBool>,
    follow_handle: Option<thread::JoinHandle<()>>,
    target_hwnd: Arc<Mutex<Option<isize>>>,
}

impl Default for HsOverlayRuntime {
    fn default() -> Self {
        Self::new()
    }
}

impl HsOverlayRuntime {
    pub fn new() -> Self {
        HsOverlayRuntime {
            stop: Arc::new(AtomicBool::new(false)),
            follow_handle: None,
            target_hwnd: Arc::new(Mutex::new(None)),
        }
    }

    /// 设置悬浮窗跟随的目标窗口（十进制 hwnd）。
    pub fn set_target(&self, hwnd: Option<isize>) {
        *self.target_hwnd.lock().unwrap() = hwnd;
    }

    /// 显示悬浮窗（首次创建并加点击穿透），并启动跟随线程。
    pub fn show(&mut self, app: &AppHandle) -> Result<(), String> {
        let window = match app.get_webview_window(OVERLAY_LABEL) {
            Some(window) => window,
            None => {
                let window = WebviewWindowBuilder::new(
                    app,
                    OVERLAY_LABEL,
                    WebviewUrl::App("index.html".into()),
                )
                .title("炉石教练悬浮窗")
                .inner_size(OVERLAY_WIDTH, OVERLAY_HEIGHT)
                .min_inner_size(OVERLAY_WIDTH, OVERLAY_HEIGHT)
                .decorations(false)
                .transparent(true)
                .always_on_top(true)
                .skip_taskbar(true)
                .resizable(false)
                .visible(false)
                .build()
                .map_err(|error| format!("Failed to create overlay window: {error}"))?;
                apply_click_through(&window)?;
                window
            }
        };

        #[cfg(windows)]
        window.set_always_on_top(true).map_err(|error| error.to_string())?;
        window
            .show()
            .map_err(|error| format!("Failed to show overlay window: {error}"))?;
        log::info!("Hs overlay window shown");

        self.start_follow(app);
        Ok(())
    }

    /// 隐藏悬浮窗并停止跟随线程。
    pub fn hide(&mut self, app: &AppHandle) {
        self.stop_follow();
        if let Some(window) = app.get_webview_window(OVERLAY_LABEL) {
            let _ = window.hide();
            log::info!("Hs overlay window hidden");
        }
    }

    fn start_follow(&mut self, app: &AppHandle) {
        if self.follow_handle.is_some() {
            return;
        }

        self.stop.store(false, Ordering::Relaxed);
        let stop = self.stop.clone();
        let target_hwnd = self.target_hwnd.clone();
        let app_handle = app.clone();

        let handle = thread::spawn(move || {
            while !stop.load(Ordering::Relaxed) {
                let target = *target_hwnd.lock().unwrap();
                let Some(window) = app_handle.get_webview_window(OVERLAY_LABEL) else {
                    break;
                };

                match target.and_then(get_window_rect) {
                    Some(rect) => {
                        let x = rect.right - OVERLAY_WIDTH as i32 - OVERLAY_MARGIN_RIGHT;
                        let y = rect.top + OVERLAY_OFFSET_TOP;
                        let _ = window.set_position(Position::Physical(PhysicalPosition::new(
                            x.max(0),
                            y.max(0),
                        )));
                        let _ = window.show();
                    }
                    None => {
                        // 目标窗口不存在/不可见时隐藏悬浮窗，避免残留
                        let _ = window.hide();
                    }
                }

                thread::sleep(Duration::from_millis(FOLLOW_POLL_MS));
            }
        });

        self.follow_handle = Some(handle);
    }

    fn stop_follow(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(handle) = self.follow_handle.take() {
            let _ = handle.join();
        }
    }
}

impl Drop for HsOverlayRuntime {
    fn drop(&mut self) {
        self.stop_follow();
    }
}

/// 加点击穿透（WS_EX_LAYERED | WS_EX_TRANSPARENT），鼠标事件直达游戏窗口。
#[cfg(windows)]
fn apply_click_through(window: &WebviewWindow) -> Result<(), String> {
    let raw = window
        .window_handle()
        .map_err(|error| format!("Failed to get overlay window handle: {error}"))?;
    let RawWindowHandle::Win32(handle) = raw.as_raw() else {
        return Err("Overlay window is not a Win32 window".to_string());
    };
    let hwnd = handle.hwnd.get() as isize;

    let style = unsafe { GetWindowLongPtrW(hwnd, GWL_EXSTYLE) };
    if style == 0 {
        return Err(format!(
            "GetWindowLongPtrW failed: {}",
            std::io::Error::last_os_error()
        ));
    }

    let new_style = style | WS_EX_LAYERED | WS_EX_TRANSPARENT;
    let result = unsafe { SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new_style) };
    if result == 0 {
        return Err(format!(
            "SetWindowLongPtrW failed: {}",
            std::io::Error::last_os_error()
        ));
    }
    log::debug!("Overlay window click-through applied: hwnd={hwnd}");
    Ok(())
}

#[cfg(not(windows))]
fn apply_click_through(_window: &WebviewWindow) -> Result<(), String> {
    // 非 Windows 平台不做点击穿透（客户端目前仅面向 Windows）
    Ok(())
}

#[cfg(windows)]
fn get_window_rect(hwnd: isize) -> Option<Rect> {
    let mut rect = Rect {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
    };
    let ok = unsafe { GetWindowRect(hwnd, &mut rect) };
    if ok == 0 {
        return None;
    }
    if rect.right - rect.left <= 0 || rect.bottom - rect.top <= 0 {
        return None;
    }
    Some(rect)
}

#[cfg(not(windows))]
fn get_window_rect(_hwnd: isize) -> Option<Rect> {
    None
}

#[cfg(not(windows))]
struct Rect;
