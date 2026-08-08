"""hscoach 配置持久化（打包成品的运行配置）。

配置存 %APPDATA%\\NTEToolbox\\hscoach\\config.json，可用 HSCOACH_CONFIG
环境变量覆盖路径（测试用）。首次运行没有 API key 时由入口引导输入并保存，
之后每次启动免输入。

优先级：命令行参数 > 环境变量（DEEPSEEK_API_KEY）> 配置文件 > 代码默认值。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_ENV = "HSCOACH_CONFIG"  # 覆盖配置文件路径（测试/自定义用）
CONFIG_DIR_NAME = "NTEToolbox"
APP_DIR_NAME = "hscoach"

# 与 coach.py 的默认值保持一致（此处手写一份避免循环导入）
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


@dataclass
class CoachConfig:
    """运行配置。friendly_player_id=None 表示日志自动校准。"""

    api_key: str = ""
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    friendly_player_id: int | None = None


def config_path() -> Path:
    """配置文件路径（默认 APPDATA\\NTEToolbox\\hscoach\\config.json）。"""
    override = os.environ.get(CONFIG_ENV)
    if override:
        return Path(override)
    local = os.environ.get("APPDATA", "")
    return Path(local) / CONFIG_DIR_NAME / APP_DIR_NAME / "config.json"


def load_config(path: Path | None = None) -> CoachConfig:
    """读取配置；文件不存在或损坏时回退默认值。"""
    p = path or config_path()
    cfg = CoachConfig()
    if not p.exists():
        return cfg
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("配置读取失败（使用默认值）：%s", e)
        return cfg
    if not isinstance(data, dict):
        logger.warning("配置内容不是对象（使用默认值）：%r", data)
        return cfg
    cfg.api_key = str(data.get("api_key", ""))
    cfg.model = str(data.get("model", DEFAULT_MODEL))
    cfg.base_url = str(data.get("base_url", DEFAULT_BASE_URL))
    fp = data.get("friendly_player_id")
    if isinstance(fp, int):
        cfg.friendly_player_id = fp
    return cfg


def save_config(cfg: CoachConfig, path: Path | None = None) -> Path:
    """保存配置（原子写：临时文件 + replace）。"""
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(p)
    return p


def effective_config(
    cli_key: str | None,
    cli_model: str | None = None,
    cli_base_url: str | None = None,
    cli_friendly: int | None = None,
    env: dict | None = None,
) -> CoachConfig:
    """解析生效配置：命令行 > 环境变量 > 配置文件 > 默认值。

    cli_key 显式传了（含显式空串）→ 尊重不回退（显式空 = 强制不配置）；
    cli_key 为 None → 环境变量 → 配置文件。
    """
    env = env if env is not None else os.environ
    file_cfg = load_config()
    if cli_key is not None:
        api_key = cli_key
    else:
        api_key = env.get("DEEPSEEK_API_KEY", "") or file_cfg.api_key
    return CoachConfig(
        api_key=api_key,
        model=cli_model or file_cfg.model,
        base_url=cli_base_url or file_cfg.base_url,
        friendly_player_id=cli_friendly if cli_friendly is not None else file_cfg.friendly_player_id,
    )
