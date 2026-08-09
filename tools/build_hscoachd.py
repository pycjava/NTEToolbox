"""PyInstaller 构建 hscoachd（客户端内置的炉石教练 headless 后端）。

产物：dist/hscoachd/（onedir：hscoachd.exe + _internal/ + data/ 离线卡库）。
与独立版 HsCoach 的区别：入口相同（tools/hscoachd_entry.py），但客户端
以 --no-overlay 方式运行它，不弹 UI。

构建后把离线卡牌库拷到 exe 旁 data/（frozen 模式下 CardDatabase 从
sys.executable 同目录 data/ 读取）。
"""

from __future__ import annotations

import shutil
from pathlib import Path


def build_pyinstaller_args(root: Path | str | None = None) -> list[str]:
    project_root = (
        Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    )
    pyinstaller_dir = project_root / "build" / "pyinstaller-hscoachd"

    return [
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name=hscoachd",
        f"--paths={project_root}",
        f"--distpath={project_root / 'dist'}",
        f"--workpath={pyinstaller_dir}",
        f"--specpath={pyinstaller_dir}",
        # hslog/hearthstone 内有函数级/懒加载导入，collect-submodules 兜底
        "--collect-submodules=hslog",
        "--collect-submodules=hearthstone",
        str(project_root / "tools" / "hscoachd_entry.py"),
    ]


def bundle_card_database(project_root: Path) -> None:
    """把离线卡牌库拷到 dist/hscoachd/data/（frozen 模式读取位置）。"""
    source_data = project_root / "hscoach" / "data"
    target_data = project_root / "dist" / "hscoachd" / "data"
    if not source_data.is_dir():
        raise FileNotFoundError(f"卡牌库目录不存在: {source_data}")

    target_data.mkdir(parents=True, exist_ok=True)
    copied = 0
    for card_file in source_data.glob("cards.*.json"):
        shutil.copy2(card_file, target_data / card_file.name)
        copied += 1
    if copied == 0:
        raise FileNotFoundError(f"卡牌库目录为空: {source_data}")


def main(argv: object | None = None) -> None:
    if argv is not None:
        raise ValueError("build_hscoachd does not accept custom arguments")

    from PyInstaller.__main__ import run

    project_root = Path(__file__).resolve().parents[1]
    run(build_pyinstaller_args(project_root))
    bundle_card_database(project_root)
    print(f"hscoachd 就绪: {project_root / 'dist' / 'hscoachd'}")


if __name__ == "__main__":
    main()
