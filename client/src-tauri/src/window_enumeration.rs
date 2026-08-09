use serde::{Deserialize, Serialize};

/// 窗口信息，返回给前端用于下拉框展示
#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WindowInfo {
    /// 窗口句柄（十进制字符串），兼容现有 parse_window_id
    pub hwnd: String,
    /// 窗口标题
    pub title: String,
    /// 窗口类名
    pub class_name: String,
}

// ── Win32 FFI ────────────────────────────────────────────────────────

type WndHandle = isize;
type WndBool = i32;
type LParam = isize;

#[link(name = "user32")]
extern "system" {
    fn EnumWindows(
        lpenumfunc: Option<unsafe extern "system" fn(WndHandle, LParam) -> WndBool>,
        lparam: LParam,
    ) -> WndBool;

    fn GetWindowTextW(hwnd: WndHandle, lpstring: *mut u16, nmaxcount: i32) -> i32;

    fn GetClassNameW(hwnd: WndHandle, lpclassname: *mut u16, nmaxcount: i32) -> i32;

    fn IsWindowVisible(hwnd: WndHandle) -> WndBool;
}

/// EnumWindows 回调：收集可见且有标题的窗口
unsafe extern "system" fn enum_windows_callback(hwnd: WndHandle, lparam: LParam) -> WndBool {
    // 跳过不可见窗口
    if IsWindowVisible(hwnd) == 0 {
        return 1; // continue
    }

    // 读取窗口标题
    let mut title_buf = [0u16; 512];
    let title_len = GetWindowTextW(hwnd, title_buf.as_mut_ptr(), title_buf.len() as i32);
    if title_len == 0 {
        return 1; // 无标题，跳过
    }
    let title = String::from_utf16_lossy(&title_buf[..title_len as usize]);

    // 读取窗口类名
    let mut class_buf = [0u16; 256];
    let class_len = GetClassNameW(hwnd, class_buf.as_mut_ptr(), class_buf.len() as i32);
    let class_name = if class_len > 0 {
        String::from_utf16_lossy(&class_buf[..class_len as usize])
    } else {
        String::new()
    };

    // 写入调用方提供的 Vec
    let windows = &mut *(lparam as *mut Vec<WindowInfo>);
    windows.push(WindowInfo {
        hwnd: hwnd.to_string(),
        title,
        class_name,
    });

    1 // continue enumeration
}

/// 枚举所有可见且有标题的桌面窗口
pub fn enumerate_visible_windows() -> Result<Vec<WindowInfo>, String> {
    let mut windows: Vec<WindowInfo> = Vec::new();

    let result = unsafe {
        EnumWindows(
            Some(enum_windows_callback),
            &mut windows as *mut Vec<WindowInfo> as LParam,
        )
    };

    if result == 0 {
        return Err("EnumWindows failed".to_string());
    }

    Ok(windows)
}
