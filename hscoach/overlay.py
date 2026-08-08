"""T8(08) 最简置顶窗 UI（一期 overlay）。

用 tkinter（Python 标准库）实现两个常驻置顶窗口：
- 建议窗：只显示建议内容，默认点击穿透（不挡游戏操作），可切换
- 控制窗：独立小窗，永不穿透——退出/再想想/穿透切换/还原日志配置
  按钮都在这。修复了"整窗 WS_EX_TRANSPARENT 导致退出按钮不可达"的 bug：
  穿透只作用于建议窗，控制窗永远可点（永不穿透的退出按钮）。
- 点击模式开启后自动回锁（AUTO_RELOCK_MS 无操作回到穿透），防忘切
- 界面含"AI 建议、非最优解"的诚实标注

不做真窗口级 overlay（三期 C# WPF）；一期是独立置顶窗，已够用。
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 500  # 文件刷新轮询间隔（tkinter after）
AUTO_RELOCK_MS = 20_000  # 点击模式自动回锁时长

# kind → 图标（唯一词典，测试复用）
KIND_ICONS = {"play": "⚔️", "trade": "🔄", "pass": "⏭", "uncertain": "❓"}


def parse_display_fields(data: dict) -> dict:
    """把 advice.json 解析成显示字段（纯函数，不依赖 tkinter，可测试）。"""
    advice = data.get("advice", {})
    turn = data.get("turn", "?")
    kind = advice.get("kind", "")
    headline = advice.get("headline", "")
    why = advice.get("why", "")
    steps = advice.get("steps", [])
    warning = advice.get("warning", "")

    kind_icon = KIND_ICONS.get(kind, "")
    display_headline = f"T{turn} {kind_icon} {headline}"
    steps_text = "\n".join(f"• {s}" for s in steps) if steps else ""
    if warning:
        steps_text = (steps_text + "\n" if steps_text else "") + f"⚠ {warning}"
    return {
        "headline": display_headline,
        "why": why,
        "steps": steps_text,
    }


class OverlayApp:
    """置顶建议窗 + 独立控制窗。非阻塞启动；文件变化时刷新内容。"""

    def __init__(self, advice_path: Path, on_manual_trigger=None, on_restore_log_config=None):
        self.advice_path = advice_path
        self.on_manual_trigger = on_manual_trigger
        self.on_restore_log_config = on_restore_log_config
        self._click_through = True
        self._last_mtime: float = 0
        self._mode_btn = None  # 穿透切换按钮（控制窗里，run() 时创建）

    def run(self) -> None:
        import tkinter as tk

        self.root = tk.Tk()
        self.root.title("炉石教练")
        self.root.geometry("360x260+50+50")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e2e")

        # 诚实标注
        title = tk.Label(
            self.root,
            text="🤖 AI 建议（非最优解，仅供参考）",
            fg="#cdd6f4",
            bg="#1e1e2e",
            font=("Microsoft YaHei", 9, "bold"),
        )
        title.pack(pady=(6, 2))

        # 建议内容区
        self.headline_var = tk.StringVar(value="等待对局开始…")
        self.why_var = tk.StringVar(value="")
        self.steps_var = tk.StringVar(value="")

        headline_lbl = tk.Label(
            self.root,
            textvariable=self.headline_var,
            fg="#a6e3a1",
            bg="#1e1e2e",
            wraplength=330,
            font=("Microsoft YaHei", 11, "bold"),
            justify="left",
        )
        headline_lbl.pack(pady=4, padx=8, anchor="w")

        why_lbl = tk.Label(
            self.root,
            textvariable=self.why_var,
            fg="#89b4fa",
            bg="#1e1e2e",
            wraplength=330,
            font=("Microsoft YaHei", 9),
            justify="left",
        )
        why_lbl.pack(pady=2, padx=8, anchor="w")

        steps_lbl = tk.Label(
            self.root,
            textvariable=self.steps_var,
            fg="#f9e2af",
            bg="#1e1e2e",
            wraplength=330,
            font=("Microsoft YaHei", 9),
            justify="left",
        )
        steps_lbl.pack(pady=2, padx=8, anchor="w")

        # 应用初始穿透（只作用于建议窗）
        self._apply_click_through()

        # 独立控制窗：永不穿透（用户唯一的操作/退出入口）
        self._build_control_window()

        # 启动轮询刷新
        self._poll_file()

        self.root.mainloop()

    def _build_control_window(self) -> None:
        import tkinter as tk

        ctrl = tk.Toplevel(self.root)
        ctrl.title("炉石教练控制")
        ctrl.attributes("-topmost", True)
        ctrl.configure(bg="#313244")
        # 放在屏幕右上角，不挡游戏主要区域
        x = self.root.winfo_screenwidth() - 300
        ctrl.geometry(f"290x120+{x}+50")

        def btn(text, command, bg="#45475a", fg="#cdd6f4", bold=False):
            return tk.Button(
                ctrl,
                text=text,
                command=command,
                bg=bg,
                fg=fg,
                relief="flat",
                font=("Microsoft YaHei", 9, "bold" if bold else "normal"),
            )

        row1 = tk.Frame(ctrl, bg="#313244")
        row1.pack(fill="x", padx=4, pady=(4, 0))
        row2 = tk.Frame(ctrl, bg="#313244")
        row2.pack(fill="x", padx=4, pady=4)

        refresh_btn = btn("🔄 再想想", self._on_refresh)
        refresh_btn.pack(side="left", padx=2)

        self._mode_btn = btn("🖱 关闭穿透", self._toggle_click_through)
        self._mode_btn.pack(side="left", padx=2)

        restore_btn = btn("↩ 还原日志配置", self._on_restore_log_config, bg="#585b70")
        restore_btn.pack(side="left", padx=2)

        quit_btn = btn("⏻ 退出", self.root.destroy, bg="#f38ba8", fg="#1e1e2e", bold=True)
        quit_btn.pack(side="right", padx=2)

        self._ctrl_status_var = tk.StringVar(value="")
        status_lbl = tk.Label(
            ctrl, textvariable=self._ctrl_status_var, fg="#a6e3a1",
            bg="#313244", font=("Microsoft YaHei", 8), anchor="w",
        )
        status_lbl.pack(fill="x", padx=6, pady=(0, 4))

        self._ctrl = ctrl

    def _apply_click_through(self) -> None:
        """切换建议窗点击穿透（Windows 专用，非 Windows 静默忽略）。

        只作用于建议窗；控制窗永不设置 WS_EX_TRANSPARENT。
        """
        import sys

        if sys.platform != "win32":
            return
        try:
            import ctypes

            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if self._click_through:
                style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as e:  # 非致命
            logger.debug("点击穿透切换失败（非致命）：%s", e)

    def _toggle_click_through(self) -> None:
        self._click_through = not self._click_through
        self._apply_click_through()
        if self._mode_btn is not None:
            self._mode_btn.config(text="🖱 关闭穿透" if self._click_through else "🖱 开启穿透")
        if not self._click_through:
            # 进入点击模式 → 定时自动回锁，防忘切挡住游戏
            self.root.after(AUTO_RELOCK_MS, self._auto_relock)

    def _auto_relock(self) -> None:
        if not self._click_through:
            logger.info("点击模式超时，自动回锁为穿透模式")
            self._toggle_click_through()

    def _on_refresh(self) -> None:
        """手动触发'再想想'。"""
        if self.on_manual_trigger:
            threading.Thread(target=self.on_manual_trigger, daemon=True).start()

    def _on_restore_log_config(self) -> None:
        """一键回滚 log.config（spec 02 的入口）。"""
        if self.on_restore_log_config is None:
            self._ctrl_status_var.set("未提供还原回调")
            return

        def worker():
            try:
                msg = self.on_restore_log_config()
            except Exception as e:  # 非致命
                msg = f"还原失败：{e}"
            self.root.after(0, lambda: self._ctrl_status_var.set(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_file(self) -> None:
        """轮询 advice.json 的 mtime，变化时刷新显示。"""
        try:
            if self.advice_path.exists():
                mtime = self.advice_path.stat().st_mtime
                if mtime != self._last_mtime:
                    self._last_mtime = mtime
                    self._load_and_display()
        except OSError:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_file)

    def _load_and_display(self) -> None:
        try:
            data = json.loads(self.advice_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        fields = parse_display_fields(data)
        self.headline_var.set(fields["headline"])
        self.why_var.set(fields["why"])
        self.steps_var.set(fields["steps"])

    def refresh_now(self) -> None:
        """供外部调用的立即刷新。"""
        self._load_and_display()
