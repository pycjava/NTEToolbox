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
                        // 目标窗口不存在/不可见时不移动、不隐藏：
                        // 窗口停留在上次位置，显示/隐藏完全由用户操作决定。
                        // （若在这里 hide，点击「显示悬浮窗」后窗口会被
                        //   立即隐藏，表现为悬浮窗"不弹"。）
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

/// 加点击穿透：用 tauri 官方的 set_ignore_cursor_events。
///
/// 不要手动 SetWindowLongPtrW 设 WS_EX_TRANSPARENT|WS_EX_LAYERED：
/// tauri/tao 在 show() 等操作时会按 WindowFlags 全量重算窗口样式，
/// 手动修改会被覆盖（实测 show 后 exstyle 从 0xc0138 回到 0x40118）。
/// set_ignore_cursor_events 设置 IGNORE_CURSOR_EVENT flag，由 tao
/// 统一管理（window_state 重算时自动带上 WS_EX_TRANSPARENT|WS_EX_LAYERED）。
#[cfg(windows)]
fn apply_click_through(window: &WebviewWindow) -> Result<(), String> {
    window
        .set_ignore_cursor_events(true)
        .map_err(|error| format!("Failed to enable click-through: {error}"))
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

#[cfg(test)]
mod tests {
    use super::*;

    /// 回归测试：真实创建 overlay 窗口后，必须保持可见（"一闪而过"回归），
    /// 且点击穿透样式（LAYERED|TRANSPARENT）已生效。
    #[test]
    fn overlay_window_stays_visible_with_click_through() {
        let app = tauri::Builder::default()
            .any_thread()
            .build(tauri::generate_context!())
            .expect("build app");
        let handle = app.handle();
        let mut overlay = HsOverlayRuntime::new();

        overlay.show(&handle).expect("show overlay");

        // 等窗口与 WebView 初始化
        std::thread::sleep(Duration::from_millis(1_500));

        let window = handle
            .get_webview_window(OVERLAY_LABEL)
            .expect("overlay window exists");
        assert!(
            window.is_visible().expect("visible check"),
            "overlay window should be visible after show"
        );

        #[cfg(windows)]
        {
            use raw_window_handle::RawWindowHandle;
            const GWL_EXSTYLE: i32 = -20;
            const WS_EX_LAYERED: isize = 0x00080000;
            const WS_EX_TRANSPARENT: isize = 0x00000020;
            #[link(name = "user32")]
            extern "system" {
                fn GetWindowLongPtrW(hwnd: isize, index: i32) -> isize;
            }
            let raw = window.window_handle().expect("hwnd");
            let RawWindowHandle::Win32(h) = raw.as_raw() else {
                panic!("overlay window is not a Win32 window");
            };
            let hwnd = h.hwnd.get() as isize;
            let style = unsafe { GetWindowLongPtrW(hwnd, GWL_EXSTYLE) };
            assert_ne!(style, 0, "GetWindowLongPtrW failed");
            assert_ne!(style & WS_EX_LAYERED, 0, "window must be layered (transparent)");
            assert_ne!(
                style & WS_EX_TRANSPARENT,
                0,
                "window must be click-through"
            );
        }

        // 再等 1 秒：窗口不得自动消失（用户报告"一闪而过"）
        std::thread::sleep(Duration::from_millis(1_000));
        assert!(
            window.is_visible().expect("visible check 2"),
            "overlay window must not vanish after showing"
        );

        overlay.hide(&handle);
    }
}
