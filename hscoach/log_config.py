"""T1(02) 炉石日志自动开启 + tail 监听。

自动写炉石的 log.config 开启 Power 模块日志（HDT 同款做法），
首次运行弹窗说明 + 备份原文件供一键回滚。
随后 tail Power.log 新增内容交给解析。

⚠️ 此模块会修改用户炉石客户端配置——所有写操作前必须备份，
并明确告知用户。绝不静默修改。

log.config 格式（HDT 标准）：
    [Zone]
    Verbosity=1
    [Power]
    Verbosity=1
    [GameState]
    Verbosity=1
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# 炉石可能的安装目录
_HEARTHSTONE_INSTALL_CANDIDATES = [
    Path(os.environ.get("ProgramFiles(X86)", r"C:\Program Files (x86)")) / "Hearthstone",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Hearthstone",
]


def _registry_install_dirs() -> list[Path]:
    """从注册表 Uninstall 键读炉石安装目录（自定义安装路径兜底）。

    战网安装炉石时无论装到哪个盘，都会写
    Uninstall\\Hearthstone 的 InstallLocation（如 C:\\bz\\Hearthstone）。
    仅 Windows；任何读注册表失败都静默跳过（返回已收集到的部分）。
    """
    if sys.platform != "win32":
        return []
    import winreg

    results: list[Path] = []
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for sub in (
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Hearthstone",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Hearthstone",
        ):
            try:
                with winreg.OpenKey(root, sub) as key:
                    location, _ = winreg.QueryValueEx(key, "InstallLocation")
            except OSError:
                continue
            if location:
                results.append(Path(location))
    return results


def hearthstone_install_dir() -> Path | None:
    """返回炉石安装目录。

    先查常见候选目录，再兜底注册表 InstallLocation（自定义安装路径，
    如 C:\\bz\\Hearthstone——候选写死会漏检导致 Power.log 永远找不到）。
    """
    for candidate in [*_HEARTHSTONE_INSTALL_CANDIDATES, *_registry_install_dirs()]:
        if (candidate / "Hearthstone.exe").exists():
            return candidate
    return None


# 炉石 LocalAppData 路径
def hearthstone_data_dir() -> Path:
    """返回炉石的 LocalAppData 目录（log.config 所在）。"""
    local = os.environ.get("LOCALAPPDATA", "")
    return Path(local) / "Blizzard" / "Hearthstone"


def log_config_path() -> Path:
    """log.config 在 LocalAppData（全球版和国服都从这里读）。"""
    return hearthstone_data_dir() / "log.config"


def power_log_path() -> Path:
    """返回最新的 Power.log 路径。

    国服炉石把日志写在安装目录的 Logs/时间戳子目录/ 下（每次启动新建子目录）。
    全球版写在 LocalAppData/Blizzard/Hearthstone/Logs/Power.log。
    本函数自动检测两种路径，返回最新的 Power.log。
    """
    # 1. 先查安装目录的时间戳子目录（国服）
    install = hearthstone_install_dir()
    if install:
        logs_root = install / "Logs"
        if logs_root.exists():
            # 找所有含 Power.log 的时间戳子目录，取最新的
            candidates = sorted(
                (d for d in logs_root.iterdir() if d.is_dir() and (d / "Power.log").exists()),
                key=lambda d: d.name,
                reverse=True,
            )
            if candidates:
                return candidates[0] / "Power.log"

    # 2. 回退到 LocalAppData（全球版 / HDT 标准）
    return hearthstone_data_dir() / "Logs" / "Power.log"


# HDT 标准的 log.config 内容（开启 Power/Zone/GameState/LoadingScreen）
# 每个段必须独立设置 FilePrinting=true，否则炉石不写日志文件
LOG_CONFIG_CONTENT = """[Power]
LogLevel=1
FilePrinting=true
ConsolePrinting=false
ScreenPrinting=false

[Zone]
LogLevel=1
FilePrinting=true
ConsolePrinting=false
ScreenPrinting=false

[GameState]
LogLevel=1
FilePrinting=true
ConsolePrinting=false
ScreenPrinting=false

[LoadingScreen]
LogLevel=1
FilePrinting=true
ConsolePrinting=false
ScreenPrinting=false
"""

BACKUP_SUFFIX = ".bak.ntetoolbox"


@dataclass
class LogConfigStatus:
    """log.config 操作的结果状态。"""

    action: str  # "created" / "updated" / "already_ok" / "restored"
    path: str
    backup_path: str | None = None
    message: str = ""


def ensure_log_config(backup: bool = True) -> LogConfigStatus:
    """确保 log.config 存在且开启 Power 日志。

    Args:
        backup: 若覆盖已有文件，先备份（默认 True，安全第一）

    Returns:
        LogConfigStatus 描述做了什么。
    """
    target = log_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    # 已存在且内容正确 → 无需操作
    if target.exists():
        existing = target.read_text(encoding="utf-8", errors="ignore")
        if "[Power]" in existing and "FilePrinting=true" in existing:
            return LogConfigStatus(
                action="already_ok",
                path=str(target),
                message="log.config 已开启 Power 日志（FilePrinting=true），无需修改。",
            )
        # 内容不符，备份后覆盖
        bk = None
        if backup:
            bk = str(target) + BACKUP_SUFFIX
            shutil.copy2(target, bk)
        target.write_text(LOG_CONFIG_CONTENT, encoding="utf-8")
        return LogConfigStatus(
            action="updated",
            path=str(target),
            backup_path=bk,
            message="log.config 已更新（原文件已备份）。",
        )

    # 不存在，新建
    target.write_text(LOG_CONFIG_CONTENT, encoding="utf-8")
    return LogConfigStatus(
        action="created",
        path=str(target),
        message="log.config 已创建（首次启用炉石日志）。",
    )


def restore_log_config() -> LogConfigStatus:
    """一键回滚：恢复备份的 log.config。"""
    target = log_config_path()
    bk = str(target) + BACKUP_SUFFIX
    if not os.path.exists(bk):
        # 没有备份，说明是我们创建的 → 删除即可
        if target.exists():
            target.unlink()
            return LogConfigStatus(
                action="restored",
                path=str(target),
                message="已删除工具创建的 log.config（炉石将停止写日志）。",
            )
        return LogConfigStatus(
            action="restored",
            path=str(target),
            message="无需回滚（log.config 不存在且无备份）。",
        )
    # 有备份，恢复
    shutil.copy2(bk, target)
    os.remove(bk)
    return LogConfigStatus(
        action="restored",
        path=str(target),
        message="已恢复原始 log.config。",
    )


def tail_power_log(poll_interval: float = 0.5, path_provider=None):
    """生成器：持续 tail Power.log，yield 新增的行。

    文件不存在时等待其出现（炉石首次写日志会创建）。
    用于实时监听对局。

    Args:
        poll_interval: 轮询间隔（秒）
        path_provider: 返回 Power.log 路径的可调用对象（默认 power_log_path；
            测试注入用，避免 mock patch 在并发线程间互相踩踏）

    健壮性（踩坑修复）：
    - 国服每次启动炉石会新建 Logs/<时间戳>/Power.log：每次轮询重新解析
      路径，发现新路径立即切换，不依赖句柄存活。
    - 文件被重建（同路径重写/轮换）：Windows 上 st_ino 不可靠（常为 0），
      改用"文件创建时间变了 或 大小比上次观测变小"检测轮换，重建后从头
      读（含 CREATE_GAME，保证 detector.reset() 触发、跨对局状态不泄漏）。

    Args:
        poll_interval: 轮询间隔（秒）
    Yields:
        新增的日志行（含换行符）
    """
    fp = None
    open_path: Path | None = None
    # 启动时文件已存在 → 从末尾 tail（不重放启动前的历史对局：历史回合
    # 逐个触发 LLM 会阻塞 worker，实时建议/快照滞后——用户实测回归）。
    # 仅当文件"首次出现"（启动时不存在，炉石在监听后才启动）或路径
    # 变化/轮换时从头读（下方分支显式置 True / seek(0)）。
    just_appeared = False
    last_ctime: float | None = None
    last_size: int = 0

    try:
        while True:
            # 每次重解析路径：国服每次启动新建时间戳子目录，重启后要能发现
            resolve_path = path_provider or power_log_path
            path = resolve_path()
            if fp is not None and open_path != path:
                logger.info("Power.log 路径变化：%s → %s", open_path, path)
                fp.close()
                fp = None
                just_appeared = True

            if not path.exists():
                if fp is not None:
                    fp.close()
                    fp = None
                just_appeared = True
                time.sleep(poll_interval)
                continue

            # 文件被轮换（重建）→ 重新打开并从头读
            try:
                stat = path.stat()
            except OSError:
                time.sleep(poll_interval)
                continue

            if fp is None:
                fp = path.open(encoding="utf-8", errors="replace")
                if just_appeared:
                    fp.seek(0)  # 新出现/轮换的文件：从头读（含 CREATE_GAME）
                else:
                    fp.seek(0, 2)  # 已存在的文件：从末尾 tail
                just_appeared = False
                open_path = path
                last_ctime = stat.st_ctime
                last_size = stat.st_size
            else:
                # 轮换检测：Windows 上 st_ctime=文件创建时间（写追加不变，
                # 重建才变）；POSIX 上 st_ctime 每次写入都变，只靠大小倒退
                # （重建的文件比上次观测小）判定。
                if sys.platform == "win32":
                    rotated = stat.st_ctime != last_ctime or stat.st_size < last_size
                else:
                    rotated = stat.st_size < last_size
                if rotated:
                    logger.info("检测到 Power.log 轮换（重建），从头读")
                    fp.close()
                    fp = path.open(encoding="utf-8", errors="replace")
                    fp.seek(0)
                    open_path = path
                    last_ctime = stat.st_ctime
                    last_size = stat.st_size
                else:
                    last_ctime = stat.st_ctime
                    last_size = stat.st_size

            # 读新增行
            for line in fp:
                yield line

            time.sleep(poll_interval)
    finally:
        # 生成器被 close() 或 GC 时，确保文件句柄释放
        if fp:
            try:
                fp.close()
            except OSError:
                pass
