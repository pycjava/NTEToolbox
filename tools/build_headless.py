"""组装无 GUI 的 headless 分发包（macos/linux/android/win × arch）。

替代已删除的 install.py 的非 GUI 路径：下载 MaaFramework 到 deps/ 后，
把 Maa 运行时 + 资源 + agent（Windows 用打包的 agent.exe，其余平台用
agent/ 源码目录，接口 child_exec 相应改写）组装成可直接使用的目录。

用法（与旧 install.yml 矩阵一致）：
    python tools/build_headless.py --version v2.0.0 --os win --arch x86_64
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

working_dir: Path = Path(__file__).parent.parent.resolve()


def strip_jsonc_comments(text: str) -> str:
    """剥离 JSONC 注释（与 validate_schema 一致的最小实现，避免依赖）。"""
    result = []
    i = 0
    n = len(text)
    in_string = False
    quote = ""
    escaped = False
    while i < n:
        ch = text[i]
        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_string = False
            i += 1
            continue
        if ch in "\"'":
            in_string = True
            quote = ch
            result.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            result.append("\n")
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assemble headless NTEToolbox bundle")
    parser.add_argument("--version", required=True, help="Version tag, e.g., v2.0.0")
    parser.add_argument(
        "--os",
        required=True,
        choices=["win", "macos", "linux", "android"],
        help="Target OS",
    )
    parser.add_argument(
        "--arch",
        required=True,
        choices=["aarch64", "x86_64"],
        help="Target architecture",
    )
    parser.add_argument(
        "--install-dir",
        default=None,
        help="Output install directory. Defaults to ./install under the repository root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    install_path = Path(args.install_dir) if args.install_dir else working_dir / "install"

    deps_bin = working_dir / "deps" / "bin"
    if not deps_bin.is_dir():
        print('Please download the MaaFramework to "deps" first.')
        print('请先下载 MaaFramework 到 "deps"。')
        return 1

    if install_path.exists():
        shutil.rmtree(install_path)
    install_path.mkdir(parents=True)

    # 1. Maa 运行时（bin 下全部内容，含 MaaPiCli 与各 ControlUnit）
    shutil.copytree(deps_bin, install_path, dirs_exist_ok=True)
    # 2. 流水线资源（资产资源目录）
    shutil.copytree(
        working_dir / "assets" / "resource",
        install_path / "resource",
        dirs_exist_ok=True,
    )

    # 3. agent：Windows 用打包 exe，其余平台用源码目录（python -m agent）
    agent_exe = working_dir / "dist" / "agent.exe"
    use_packaged_agent = args.os == "win" and agent_exe.is_file()
    if use_packaged_agent:
        shutil.copy2(agent_exe, install_path / "agent.exe")
    else:
        shutil.copytree(
            working_dir / "agent",
            install_path / "agent",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            dirs_exist_ok=True,
        )

    # 4. interface.json：从 interface.jsonc 生成，agent 入口按平台改写
    interface_text = (working_dir / "assets" / "interface.jsonc").read_text(
        encoding="utf-8"
    )
    interface = json.loads(strip_jsonc_comments(interface_text))
    if use_packaged_agent:
        interface["agent"] = {"child_exec": "./agent.exe", "child_args": []}
    else:
        interface["agent"] = {"child_exec": "python", "child_args": ["-u", "-m", "agent"]}
    (install_path / "interface.json").write_text(
        json.dumps(interface, ensure_ascii=False, indent=3) + "\n",
        encoding="utf-8",
    )

    # 5. 文档与版本标记
    for name in ("README.md", "LICENSE"):
        source = working_dir / name
        if source.is_file():
            shutil.copy2(source, install_path / name)
    (install_path / "VERSION").write_text(args.version + "\n", encoding="utf-8")

    print(f"Headless bundle ready: {install_path} ({args.os}/{args.arch})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
