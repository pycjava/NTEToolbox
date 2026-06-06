//! 窗口截屏模块 — 使用 Win32 PrintWindow 捕获目标窗口画面，编码为 JPEG

use std::io::Cursor;

// ── Win32 类型别名 ────────────────────────────────────────────────────

type WndHandle = isize;
type HdcHandle = isize;
type HBitmap = isize;
type HGdiObj = isize;
type Bool = i32;
type DWord = u32;
type Word = u16;

// ── Win32 结构体 ──────────────────────────────────────────────────────

#[repr(C)]
struct RECT {
    left: i32,
    top: i32,
    right: i32,
    bottom: i32,
}

#[repr(C)]
struct BITMAPINFOHEADER {
    bi_size: DWord,
    bi_width: i32,
    bi_height: i32,
    bi_planes: Word,
    bi_bit_count: Word,
    bi_compression: DWord,
    bi_size_image: DWord,
    bi_x_pels_per_meter: i32,
    bi_y_pels_per_meter: i32,
    bi_clr_used: DWord,
    bi_clr_important: DWord,
}

// ── Win32 FFI 声明 ───────────────────────────────────────────────────

const PW_RENDERFULLCONTENT: DWord = 2;
const DIB_RGB_COLORS: DWord = 0;

#[link(name = "user32")]
extern "system" {
    fn GetWindowDC(hwnd: WndHandle) -> HdcHandle;
    fn ReleaseDC(hwnd: WndHandle, hdc: HdcHandle) -> i32;
    fn GetWindowRect(hwnd: WndHandle, lprect: *mut RECT) -> Bool;
    fn PrintWindow(hwnd: WndHandle, hdcblit: HdcHandle, nflags: DWord) -> Bool;
}

#[link(name = "gdi32")]
extern "system" {
    fn CreateCompatibleDC(hdc: HdcHandle) -> HdcHandle;
    fn CreateCompatibleBitmap(hdc: HdcHandle, width: i32, height: i32) -> HBitmap;
    fn SelectObject(hdc: HdcHandle, hgdiobj: HGdiObj) -> HGdiObj;
    fn GetDIBits(
        hdc: HdcHandle,
        hbm: HBitmap,
        start: DWord,
        cscanlines: DWord,
        lpvbits: *mut u8,
        lpbi: *mut BITMAPINFOHEADER,
        usage: DWord,
    ) -> i32;
    fn DeleteDC(hdc: HdcHandle) -> Bool;
    fn DeleteObject(ho: HGdiObj) -> Bool;
}

// ── 公开接口 ─────────────────────────────────────────────────────────

/// 捕获指定窗口的截图，返回原始 JPEG 字节。
pub fn capture_window_jpeg(hwnd_str: &str) -> Result<Vec<u8>, String> {
    let hwnd = parse_hwnd(hwnd_str)?;
    if hwnd == 0 {
        return Err("无效的窗口句柄".to_string());
    }

    unsafe {
        // 1. 获取窗口整体尺寸
        let mut rect = RECT {
            left: 0,
            top: 0,
            right: 0,
            bottom: 0,
        };
        if GetWindowRect(hwnd, &mut rect) == 0 {
            return Err("目标窗口不可用".to_string());
        }
        let width = rect.right - rect.left;
        let height = rect.bottom - rect.top;
        if width <= 0 || height <= 0 {
            return Err("窗口已最小化".to_string());
        }

        // 2. 获取窗口 DC 并创建兼容内存 DC + 位图
        let hdc_window = GetWindowDC(hwnd);
        if hdc_window == 0 {
            return Err("GetWindowDC 失败".to_string());
        }

        let hdc_mem = CreateCompatibleDC(hdc_window);
        if hdc_mem == 0 {
            ReleaseDC(hwnd, hdc_window);
            return Err("CreateCompatibleDC 失败".to_string());
        }

        let h_bitmap = CreateCompatibleBitmap(hdc_window, width, height);
        if h_bitmap == 0 {
            DeleteDC(hdc_mem);
            ReleaseDC(hwnd, hdc_window);
            return Err("CreateCompatibleBitmap 失败".to_string());
        }

        // 3. 选入位图并调用 PrintWindow
        let old_obj = SelectObject(hdc_mem, h_bitmap as HGdiObj);
        let print_ok = PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT);

        if print_ok == 0 {
            SelectObject(hdc_mem, old_obj);
            DeleteObject(h_bitmap as HGdiObj);
            DeleteDC(hdc_mem);
            ReleaseDC(hwnd, hdc_window);
            return Err("PrintWindow 失败".to_string());
        }

        // 4. 提取像素数据
        // 32bpp 每行 = width * 4 字节，天然 4 字节对齐，无需额外 padding
        let stride = width as usize * 4;
        let pixel_buf_len = stride * height as usize;
        let mut pixel_buf = vec![0u8; pixel_buf_len];

        let bmi = BITMAPINFOHEADER {
            bi_size: std::mem::size_of::<BITMAPINFOHEADER>() as DWord,
            bi_width: width,
            bi_height: -height,
            bi_planes: 1,
            bi_bit_count: 32,
            bi_compression: 0,
            bi_size_image: 0,
            bi_x_pels_per_meter: 0,
            bi_y_pels_per_meter: 0,
            bi_clr_used: 0,
            bi_clr_important: 0,
        };

        let scan_result = GetDIBits(
            hdc_mem,
            h_bitmap,
            0,
            height as DWord,
            pixel_buf.as_mut_ptr(),
            &bmi as *const BITMAPINFOHEADER as *mut BITMAPINFOHEADER,
            DIB_RGB_COLORS,
        );

        // 5. 释放 GDI 资源
        SelectObject(hdc_mem, old_obj);
        DeleteObject(h_bitmap as HGdiObj);
        DeleteDC(hdc_mem);
        ReleaseDC(hwnd, hdc_window);

        if scan_result == 0 {
            return Err("GetDIBits 失败".to_string());
        }

        // 6. BGRA → RGB 批量转换（避免 put_pixel 双重循环）
        let pixel_count = width as usize * height as usize;
        let mut rgb_flat = Vec::with_capacity(pixel_count * 3);
        for chunk in pixel_buf.chunks_exact(4) {
            rgb_flat.push(chunk[2]); // R
            rgb_flat.push(chunk[1]); // G
            rgb_flat.push(chunk[0]); // B
        }
        let rgb_image = image::RgbImage::from_vec(width as u32, height as u32, rgb_flat)
            .ok_or_else(|| "图像缓冲区大小不匹配".to_string())?;

        // 7. JPEG 编码
        let mut jpeg_buf = Cursor::new(Vec::new());
        let encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut jpeg_buf, 70);
        rgb_image
            .write_with_encoder(encoder)
            .map_err(|e| format!("JPEG 编码失败: {e}"))?;

        Ok(jpeg_buf.into_inner())
    }
}

/// 解析十进制或十六进制（`0x...`）hwnd 字符串
fn parse_hwnd(s: &str) -> Result<isize, String> {
    let trimmed = s.trim();
    if trimmed.is_empty() {
        return Err("窗口句柄为空".to_string());
    }
    if let Some(hex) = trimmed.strip_prefix("0x").or_else(|| trimmed.strip_prefix("0X")) {
        isize::from_str_radix(hex, 16).map_err(|e| format!("解析十六进制句柄失败: {e}"))
    } else {
        trimmed.parse::<isize>().map_err(|e| format!("解析十进制句柄失败: {e}"))
    }
}

// ── 测试 ─────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_empty_hwnd() {
        assert!(capture_window_jpeg("").is_err());
    }

    #[test]
    fn rejects_whitespace_hwnd() {
        assert!(capture_window_jpeg("   ").is_err());
    }

    #[test]
    fn rejects_null_hwnd() {
        assert!(capture_window_jpeg("0").is_err());
    }

    #[test]
    fn rejects_nonexistent_window() {
        assert!(capture_window_jpeg("999999999").is_err());
    }

    #[test]
    fn parse_hwnd_decimal() {
        assert_eq!(parse_hwnd("12345").unwrap(), 12345isize);
    }

    #[test]
    fn parse_hwnd_hex() {
        assert_eq!(parse_hwnd("0xFF").unwrap(), 255isize);
    }

    #[test]
    fn parse_hwnd_invalid() {
        assert!(parse_hwnd("abc").is_err());
    }
}
