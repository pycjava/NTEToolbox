"""PyInstaller 构建 hscoach 成品（镜像 tools/build_agent.py 的模式）。

产物：dist/HsCoach/（onedir，双击 HsCoach.exe 即可运行）。
onedir 而非 onefile：启动快（免每次解压）、卡牌库缓存放 exe 旁 data/
可持久（onefile 在临时解压目录里每次都会丢）。

构建后由 build_hscoach.ps1 预置离线卡牌库并打 zip。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# HsCoach 的三方运行时依赖（与 pyproject.toml 的 hearthstone extra 对应）。
# 打包前必须可导入，否则 PyInstaller 会静默跳过 import httpx / hslog /
# hearthstone，产物 HsCoach.exe 启动即秒退（exit code 1）。
RUNTIME_DEPENDENCIES = ("httpx", "hslog", "hearthstone")


def verify_runtime_dependencies() -> None:
    """打包前校验运行时依赖，缺失即给出明确安装指引并退出。"""
    missing = [name for name in RUNTIME_DEPENDENCIES if importlib.util.find_spec(name) is None]
    if missing:
        raise SystemExit(
            "HsCoach 打包缺少运行时依赖: "
            + ", ".join(missing)
            + "\n请先安装 hearthstone 依赖组后重试:\n"
            + '    pip install -e ".[hearthstone]"'
        )


def build_pyinstaller_args(root: Path | str | None = None) -> list[str]:
    project_root = (
        Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    )
    pyinstaller_dir = project_root / "build" / "pyinstaller-hscoach"

    return [
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name=HsCoach",
        f"--paths={project_root}",
        f"--distpath={project_root / 'dist'}",
        f"--workpath={pyinstaller_dir}",
        f"--specpath={pyinstaller_dir}",
        # hslog/hearthstone 内有函数级/懒加载导入，collect-submodules 兜底
        "--collect-submodules=hslog",
        "--collect-submodules=hearthstone",
        str(project_root / "tools" / "hscoach_entry.py"),
    ]


def main(argv: object | None = None) -> None:
    if argv is not None:
        raise ValueError("build_hscoach does not accept custom arguments")

    from PyInstaller.__main__ import run

    verify_runtime_dependencies()
    run(build_pyinstaller_args())


if __name__ == "__main__":
    main()
