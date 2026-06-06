//! 窗口截屏模块 — 使用 Win32 PrintWindow 捕获目标窗口画面，编码为 JPEG

use std::io::Cursor;
use std::time::{Duration, Instant};

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

#[derive(Clone, Copy, Debug)]
pub struct CaptureOptions {
    pub jpeg_quality: u8,
    pub max_output_width: Option<u32>,
    pub max_output_height: Option<u32>,
    pub log_details: bool,
}

impl Default for CaptureOptions {
    fn default() -> Self {
        Self {
            jpeg_quality: 70,
            max_output_width: None,
            max_output_height: None,
            log_details: true,
        }
    }
}

impl CaptureOptions {
    fn quality(self) -> u8 {
        self.jpeg_quality.clamp(1, 100)
    }

    fn output_dimensions(self, source_width: u32, source_height: u32) -> (u32, u32) {
        let max_width = self
            .max_output_width
            .filter(|value| *value > 0)
            .unwrap_or(source_width);
        let max_height = self
            .max_output_height
            .filter(|value| *value > 0)
            .unwrap_or(source_height);

        if source_width <= max_width && source_height <= max_height {
            return (source_width, source_height);
        }

        let width_scale = max_width as f64 / source_width as f64;
        let height_scale = max_height as f64 / source_height as f64;
        let scale = width_scale.min(height_scale).min(1.0);

        (
            ((source_width as f64 * scale).round() as u32).max(1),
            ((source_height as f64 * scale).round() as u32).max(1),
        )
    }
}

#[derive(Debug)]
pub struct CaptureFrame {
    pub jpeg_bytes: Vec<u8>,
    pub stats: CaptureStats,
}

#[derive(Debug)]
pub struct CaptureStats {
    pub source_width: u32,
    pub source_height: u32,
    pub output_width: u32,
    pub output_height: u32,
    pub pixel_bytes: usize,
    pub jpeg_bytes: usize,
    pub timings: CaptureTimings,
}

#[derive(Debug)]
pub struct CaptureTimings {
    pub total: Duration,
    pub get_window_rect: Duration,
    pub prepare_gdi: Duration,
    pub print_window: Duration,
    pub get_dibits: Duration,
    pub bgra_to_rgb: Duration,
    pub resize: Duration,
    pub jpeg_encode: Duration,
}

impl CaptureStats {
    pub fn log_debug(&self) {
        log::debug!(
            "截屏耗时明细: source={}x{}, output={}x{}, pixels={} 字节, jpeg={} 字节, \
             total={:?}, GetWindowRect={:?}, prepare_gdi={:?}, PrintWindow={:?}, \
             GetDIBits={:?}, BGRA->RGB={:?}, resize={:?}, JPEG={:?}",
            self.source_width,
            self.source_height,
            self.output_width,
            self.output_height,
            self.pixel_bytes,
            self.jpeg_bytes,
            self.timings.total,
            self.timings.get_window_rect,
            self.timings.prepare_gdi,
            self.timings.print_window,
            self.timings.get_dibits,
            self.timings.bgra_to_rgb,
            self.timings.resize,
            self.timings.jpeg_encode
        );
    }
}

/// 捕获指定窗口的截图，返回原始 JPEG 字节。
#[allow(dead_code)]
pub fn capture_window_jpeg(hwnd_str: &str) -> Result<Vec<u8>, String> {
    capture_window_frame(hwnd_str, CaptureOptions::default()).map(|frame| frame.jpeg_bytes)
}

#[allow(dead_code)]
pub fn capture_window_frame(
    hwnd_str: &str,
    options: CaptureOptions,
) -> Result<CaptureFrame, String> {
    let mut session = WindowCaptureSession::new(hwnd_str)?;
    session.capture_jpeg(options)
}

pub struct WindowCaptureSession {
    hwnd: WndHandle,
    hdc_mem: HdcHandle,
    h_bitmap: HBitmap,
    old_obj: HGdiObj,
    width: i32,
    height: i32,
    pixel_buf: Vec<u8>,
}

impl WindowCaptureSession {
    pub fn new(hwnd_str: &str) -> Result<Self, String> {
        log::debug!("开始截屏: hwnd_str={hwnd_str:?}");

        let hwnd = parse_hwnd(hwnd_str)?;
        if hwnd == 0 {
            log::error!("无效的窗口句柄: hwnd=0");
            return Err("无效的窗口句柄".to_string());
        }
        log::debug!("解析句柄: hwnd={hwnd}");

        Ok(Self {
            hwnd,
            hdc_mem: 0,
            h_bitmap: 0,
            old_obj: 0,
            width: 0,
            height: 0,
            pixel_buf: Vec::new(),
        })
    }

    pub fn capture_jpeg(&mut self, options: CaptureOptions) -> Result<CaptureFrame, String> {
        let total_start = Instant::now();

        unsafe {
            let rect_start = Instant::now();
            let mut rect = RECT {
                left: 0,
                top: 0,
                right: 0,
                bottom: 0,
            };
            if GetWindowRect(self.hwnd, &mut rect) == 0 {
                log::error!("GetWindowRect 失败: hwnd={}", self.hwnd);
                return Err("目标窗口不可用".to_string());
            }
            let get_window_rect = rect_start.elapsed();

            let width = rect.right - rect.left;
            let height = rect.bottom - rect.top;
            if options.log_details {
                log::debug!(
                    "窗口尺寸: {width}x{height} (rect={},{},{},{})",
                    rect.left,
                    rect.top,
                    rect.right,
                    rect.bottom
                );
            }

            if width <= 0 || height <= 0 {
                log::warn!("窗口已最小化或尺寸无效: {width}x{height}");
                return Err("窗口已最小化".to_string());
            }

            let prepare_gdi_start = Instant::now();
            self.ensure_gdi_resources(width, height)?;
            let prepare_gdi = prepare_gdi_start.elapsed();

            let print_start = Instant::now();
            let print_ok = PrintWindow(self.hwnd, self.hdc_mem, PW_RENDERFULLCONTENT);
            let print_window = print_start.elapsed();

            if print_ok == 0 {
                log::error!("PrintWindow 失败: hwnd={}", self.hwnd);
                return Err("PrintWindow 失败".to_string());
            }
            if options.log_details {
                log::debug!("PrintWindow 成功: 耗时={print_window:?}");
            }

            // 32bpp 每行 = width * 4 字节，天然 4 字节对齐，无需额外 padding
            let stride = width as usize * 4;
            let pixel_buf_len = stride * height as usize;
            if self.pixel_buf.len() != pixel_buf_len {
                self.pixel_buf.resize(pixel_buf_len, 0);
            }

            let mut bmi = BITMAPINFOHEADER {
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

            let dibits_start = Instant::now();
            let scan_result = GetDIBits(
                self.hdc_mem,
                self.h_bitmap,
                0,
                height as DWord,
                self.pixel_buf.as_mut_ptr(),
                &mut bmi,
                DIB_RGB_COLORS,
            );
            let get_dibits = dibits_start.elapsed();

            if scan_result == 0 {
                log::error!("GetDIBits 失败: scan_result=0");
                return Err("GetDIBits 失败".to_string());
            }
            if options.log_details {
                log::debug!(
                    "GetDIBits 成功: 提取 {pixel_buf_len} 字节像素数据, 耗时={get_dibits:?}"
                );
            }

            let source_width = width as u32;
            let source_height = height as u32;
            let (output_width, output_height) =
                options.output_dimensions(source_width, source_height);

            let convert_start = Instant::now();
            let rgb_flat = bgra_to_rgb_nearest(
                &self.pixel_buf,
                source_width as usize,
                source_height as usize,
                output_width as usize,
                output_height as usize,
            );
            let bgra_to_rgb = convert_start.elapsed();
            let resize = Duration::ZERO;

            let rgb_image = image::RgbImage::from_vec(output_width, output_height, rgb_flat)
                .ok_or_else(|| {
                    log::error!("图像缓冲区大小不匹配");
                    "图像缓冲区大小不匹配".to_string()
                })?;

            let jpeg_start = Instant::now();
            let mut jpeg_buf = Cursor::new(Vec::new());
            let encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(
                &mut jpeg_buf,
                options.quality(),
            );
            rgb_image.write_with_encoder(encoder).map_err(|e| {
                log::error!("JPEG 编码失败: {e}");
                format!("JPEG 编码失败: {e}")
            })?;
            let jpeg_encode = jpeg_start.elapsed();

            let jpeg_bytes = jpeg_buf.into_inner();
            let stats = CaptureStats {
                source_width,
                source_height,
                output_width,
                output_height,
                pixel_bytes: pixel_buf_len,
                jpeg_bytes: jpeg_bytes.len(),
                timings: CaptureTimings {
                    total: total_start.elapsed(),
                    get_window_rect,
                    prepare_gdi,
                    print_window,
                    get_dibits,
                    bgra_to_rgb,
                    resize,
                    jpeg_encode,
                },
            };
            if options.log_details {
                log::debug!(
                    "截屏完成: source={}x{}, output={}x{}, JPEG 大小={} 字节",
                    source_width,
                    source_height,
                    output_width,
                    output_height,
                    jpeg_bytes.len()
                );
                stats.log_debug();
            }

            Ok(CaptureFrame { jpeg_bytes, stats })
        }
    }

    unsafe fn ensure_gdi_resources(&mut self, width: i32, height: i32) -> Result<(), String> {
        if self.hdc_mem != 0 && self.h_bitmap != 0 && self.width == width && self.height == height {
            return Ok(());
        }

        self.release_gdi_resources();

        let hdc_window = GetWindowDC(self.hwnd);
        if hdc_window == 0 {
            log::error!("GetWindowDC 失败: hwnd={}", self.hwnd);
            return Err("GetWindowDC 失败".to_string());
        }

        let hdc_mem = CreateCompatibleDC(hdc_window);
        if hdc_mem == 0 {
            log::error!("CreateCompatibleDC 失败");
            ReleaseDC(self.hwnd, hdc_window);
            return Err("CreateCompatibleDC 失败".to_string());
        }

        let h_bitmap = CreateCompatibleBitmap(hdc_window, width, height);
        ReleaseDC(self.hwnd, hdc_window);

        if h_bitmap == 0 {
            log::error!("CreateCompatibleBitmap 失败: {width}x{height}");
            DeleteDC(hdc_mem);
            return Err("CreateCompatibleBitmap 失败".to_string());
        }

        let old_obj = SelectObject(hdc_mem, h_bitmap as HGdiObj);
        if old_obj == 0 {
            log::error!("SelectObject 失败");
            DeleteObject(h_bitmap as HGdiObj);
            DeleteDC(hdc_mem);
            return Err("SelectObject 失败".to_string());
        }

        self.hdc_mem = hdc_mem;
        self.h_bitmap = h_bitmap;
        self.old_obj = old_obj;
        self.width = width;
        self.height = height;

        log::debug!(
            "GDI 对象创建成功: hdc_mem={hdc_mem}, h_bitmap={h_bitmap}, size={width}x{height}"
        );
        Ok(())
    }

    unsafe fn release_gdi_resources(&mut self) {
        if self.hdc_mem != 0 {
            if self.old_obj != 0 {
                SelectObject(self.hdc_mem, self.old_obj);
            }
            if self.h_bitmap != 0 {
                DeleteObject(self.h_bitmap as HGdiObj);
            }
            DeleteDC(self.hdc_mem);
            log::debug!("GDI 资源已释放: size={}x{}", self.width, self.height);
        }

        self.hdc_mem = 0;
        self.h_bitmap = 0;
        self.old_obj = 0;
        self.width = 0;
        self.height = 0;
    }
}

impl Drop for WindowCaptureSession {
    fn drop(&mut self) {
        unsafe {
            self.release_gdi_resources();
        }
    }
}

fn bgra_to_rgb_nearest(
    bgra: &[u8],
    source_width: usize,
    source_height: usize,
    output_width: usize,
    output_height: usize,
) -> Vec<u8> {
    let mut rgb = Vec::with_capacity(output_width * output_height * 3);
    let x_offsets: Vec<usize> = (0..output_width)
        .map(|x| (x * source_width / output_width) * 4)
        .collect();

    for output_y in 0..output_height {
        let source_y = output_y * source_height / output_height;
        let source_row = source_y * source_width * 4;

        for source_x_offset in &x_offsets {
            let source_index = source_row + source_x_offset;
            rgb.push(bgra[source_index + 2]); // R
            rgb.push(bgra[source_index + 1]); // G
            rgb.push(bgra[source_index]); // B
        }
    }

    rgb
}

/// 解析十进制或十六进制（`0x...`）hwnd 字符串
fn parse_hwnd(s: &str) -> Result<isize, String> {
    let trimmed = s.trim();
    if trimmed.is_empty() {
        return Err("窗口句柄为空".to_string());
    }
    if let Some(hex) = trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
    {
        isize::from_str_radix(hex, 16).map_err(|e| format!("解析十六进制句柄失败: {e}"))
    } else {
        trimmed
            .parse::<isize>()
            .map_err(|e| format!("解析十进制句柄失败: {e}"))
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
