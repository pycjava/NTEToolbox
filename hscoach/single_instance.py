"""hscoachd 单实例锁：防止多个教练实例同时监听同一个 Power.log。

客户端「结束教练」只停自己 spawn 的实例；升级安装/强杀客户端可能遗留
孤儿 hscoachd（不归任何客户端管理）。单实例锁让残留实例在下次启动时
被识别：已有存活实例则拒绝启动（报错退出），残留（PID 已死）则接管。

锁文件：<publish_dir>/hscoachd.lock，内容为持有者 PID。
崩溃残留自愈：锁文件在但 PID 已死 → 删除并接管。
"""

from __future__ import annotations

import os
from pathlib import Path

LOCK_FILENAME = "hscoachd.lock"


def _process_alive(pid: int) -> bool:
    """跨平台判断进程是否存活（无 psutil 依赖）。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        # Access Denied 也说明进程存在（可能权限不足，但确实活着）
        return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class SingleInstanceLock:
    """基于锁文件（PID）的单实例互斥，支持崩溃残留自愈。"""

    def __init__(self, publish_dir: Path):
        self.lock_path = publish_dir / LOCK_FILENAME

    def acquire(self) -> tuple[bool, str]:
        """尝试获取锁。

        Returns:
            (True, "") 获取成功；
            (False, 消息) 已有存活实例，拒绝启动。
        """
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # 已有锁文件：PID 存活 → 拒绝；PID 已死（残留）→ 接管
            try:
                existing = int(self.lock_path.read_text(encoding="utf-8").strip() or "0")
            except (OSError, ValueError):
                existing = 0
            if existing > 0 and _process_alive(existing):
                return False, f"另一个教练实例正在运行（PID {existing}）。请先结束它再启动。"
            try:
                self.lock_path.unlink()
            except OSError:
                pass
            return self.acquire()
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            return True, ""

    def release(self) -> None:
        try:
            self.lock_path.unlink()
        except OSError:
            pass
