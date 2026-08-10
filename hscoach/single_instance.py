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
            (False, 消息) 已有存活实例，或无法清理残留锁文件。
        """
        # 迭代而非递归：unlink 失败时旧实现会无限递归（RecursionError）。
        # 每轮重新 O_EXCL 创建：unlink 成功后不直接返回成功，而是下一轮
        # 再用 O_EXCL 确认——天然消除 TOCTOU（若期间别的进程抢占，下一轮
        # 读到其存活 PID 会拒绝）。正常路径 1-2 轮收敛。
        for _ in range(3):
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                # 已有锁文件：PID 存活 → 拒绝；PID 已死（残留）→ 尝试清理后下轮接管
                try:
                    existing = int(
                        self.lock_path.read_text(encoding="utf-8").strip() or "0"
                    )
                except (OSError, ValueError):
                    existing = 0
                if existing > 0 and _process_alive(existing):
                    return (
                        False,
                        f"另一个教练实例正在运行（PID {existing}）。请先结束它再启动。",
                    )
                try:
                    self.lock_path.unlink()
                except OSError as e:
                    # 残留锁删不掉（只读 FS / 权限不足）→ 报错而非递归
                    return (
                        False,
                        f"无法清理残留锁文件 {self.lock_path}：{e}。请手动删除后重试。",
                    )
                # unlink 成功 → 进入下一轮 O_EXCL（重新确认，防 TOCTOU）
                continue
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(str(os.getpid()))
                return True, ""

        # 理论上不可达：3 轮内未收敛（持续的并发抢占）。报错而非栈溢出。
        return False, f"获取单实例锁失败：{self.lock_path} 反复被抢占，请重试。"

    def release(self) -> None:
        try:
            self.lock_path.unlink()
        except OSError:
            pass
