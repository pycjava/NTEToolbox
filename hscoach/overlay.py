"""T8(08) 最简置顶窗 UI（一期 overlay）。

用 tkinter（Python 标准库）实现一个常驻置顶、半透明的小窗口：
- 显示 AI 教练的建议（主推荐 + 理由 + 步骤 + 警示）
- 监听 advice.json 文件变化自动刷新
- 默认点击穿透（不挡游戏操作），热键可切换
- 永不穿透的退出按钮（用户唯一的退出路径）
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


class OverlayApp:
    """置顶建议窗。非阻塞启动；文件变化时刷新内容。"""

    def __init__(self, advice_path: Path, on_manual_trigger=None):
        self.advice_path = advice_path
        self.on_manual_trigger = on_manual_trigger
        self._click_through = True
        self._last_mtime: float = 0

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

        # 底部按钮栏（永不穿透区）
        btn_frame = tk.Frame(self.root, bg="#313244")
        btn_frame.pack(side="bottom", fill="x")

        refresh_btn = tk.Button(
            btn_frame,
            text="🔄 再想想",
            command=self._on_refresh,
            bg="#45475a",
            fg="#cdd6f4",
            relief="flat",
            font=("Microsoft YaHei", 9),
        )
        refresh_btn.pack(side="left", padx=4, pady=4)

        mode_btn = tk.Button(
            btn_frame,
            text="🖱 点击模式",
            command=self._toggle_click_through,
            bg="#45475a",
            fg="#cdd6f4",
            relief="flat",
            font=("Microsoft YaHei", 9),
        )
        mode_btn.pack(side="left", padx=4, pady=4)

        quit_btn = tk.Button(
            btn_frame,
            text="⏻ 退出",
            command=self.root.destroy,
            bg="#f38ba8",
            fg="#1e1e2e",
            relief="flat",
            font=("Microsoft YaHei", 9, "bold"),
        )
        quit_btn.pack(side="right", padx=4, pady=4)

        # 应用初始穿透
        self._apply_click_through()

        # 启动轮询刷新
        self._poll_file()

        self.root.mainloop()

    def _apply_click_through(self) -> None:
        """切换点击穿透（Windows 专用，非 Windows 静默忽略）。"""
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
        except Exception as e:
            logger.debug("点击穿透切换失败（非致命）：%s", e)

    def _toggle_click_through(self) -> None:
        self._click_through = not self._click_through
        self._apply_click_through()

    def _on_refresh(self) -> None:
        """手动触发'再想想'。"""
        if self.on_manual_trigger:
            threading.Thread(target=self.on_manual_trigger, daemon=True).start()

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

        advice = data.get("advice", {})
        turn = data.get("turn", "?")
        kind = advice.get("kind", "")
        headline = advice.get("headline", "")
        why = advice.get("why", "")
        steps = advice.get("steps", [])
        warning = advice.get("warning", "")

        kind_icon = {"play": "⚔️", "trade": "🔄", "pass": "⏭", "uncertain": "❓"}.get(kind, "")
        self.headline_var.set(f"T{turn} {kind_icon} {headline}")
        self.why_var.set(why)
        steps_text = "\n".join(f"• {s}" for s in steps) if steps else ""
        if warning:
            steps_text = (steps_text + "\n" if steps_text else "") + f"⚠ {warning}"
        self.steps_var.set(steps_text)

    def refresh_now(self) -> None:
        """供外部调用的立即刷新。"""
        self._load_and_display()
