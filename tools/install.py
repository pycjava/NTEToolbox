from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import jsonc
from configure import configure_ocr_model

working_dir: Path = Path(__file__).parent.parent.resolve()
install_path: Path = working_dir / "install"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install NTEToolbox with MaaFramework and GUI"
    )
    parser.add_argument("--version", required=True, help="Version tag, e.g., v1.0.0")
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
    # 改为可选参数，非 Android 平台必须提供
    parser.add_argument(
        "--gui",
        required=False,
        default=None,
        choices=["mfaa", "mxu"],
        help="GUI type (mfaa or mxu), required for non-Android platforms",
    )
    return parser.parse_args()


def get_dotnet_platform_tag() -> str:
    """自动检测当前平台并返回对应的dotnet平台标签"""
    if os_name == "win" and arch == "x86_64":
        return "win-x64"
    if os_name == "win" and arch == "aarch64":
        return "win-arm64"
    if os_name == "macos" and arch == "x86_64":
        return "osx-x64"
    if os_name == "macos" and arch == "aarch64":
        return "osx-arm64"
    if os_name == "linux" and arch == "x86_64":
        return "linux-x64"
    if os_name == "linux" and arch == "aarch64":
        return "linux-arm64"
    # argparse 已限制选项，但保留防御代码
    print("Unsupported OS or architecture.")
    sys.exit(1)


def install_deps() -> None:
    if not (working_dir / "deps" / "bin").is_dir():
        print('Please download the MaaFramework to "deps" first.')
        print('请先下载 MaaFramework 到 "deps"。')
        sys.exit(1)

    if os_name == "android":
        shutil.copytree(
            working_dir / "deps" / "bin",
            install_path,
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "share" / "MaaAgentBinary",
            install_path / "MaaAgentBinary",
            dirs_exist_ok=True,
        )
        return

    # 非 Android 平台必须指定 GUI
    if gui is None:
        print("Error: --gui is required for non-Android platforms.")
        sys.exit(1)

    ignore_patterns = shutil.ignore_patterns(
        "*MaaDbgControlUnit*",
        "*MaaThriftControlUnit*",
        "*MaaRpc*",
        "*MaaHttp*",
        "plugins",
        "*.node",
        "*MaaPiCli*",
    )

    match gui:
        case "mfaa":
            target_dir: Path = (
                install_path / "runtimes" / get_dotnet_platform_tag() / "native"
            )
            shutil.copytree(
                working_dir / "deps" / "bin",
                target_dir,
                ignore=ignore_patterns,
                dirs_exist_ok=True,
            )
            shutil.copytree(
                working_dir / "deps" / "share" / "MaaAgentBinary",
                install_path / "libs" / "MaaAgentBinary",
                dirs_exist_ok=True,
            )
            shutil.copytree(
                working_dir / "deps" / "bin" / "plugins",
                install_path / "plugins" / get_dotnet_platform_tag(),
                dirs_exist_ok=True,
            )
        case "mxu":
            target_dir: Path = install_path / "maafw"
            shutil.copytree(
                working_dir / "deps" / "bin",
                target_dir,
                ignore=ignore_patterns,
                dirs_exist_ok=True,
            )
        case _:
            raise ValueError(f"不允许的值: --gui {gui}")


def resolve_agent_config(_root: Path, target_os: str) -> dict[str, object]:
    if target_os == "win":
        return {
            "child_exec": "./agent.exe",
            "child_args": [],
        }

    return {
        "child_exec": "python",
        "child_args": ["-u", "-m", "agent"],
    }


def install_resource() -> None:
    configure_ocr_model()

    shutil.copytree(
        working_dir / "assets" / "resource",
        install_path / "resource",
        dirs_exist_ok=True,
    )

    for interface_filename in ("interface.jsonc", "interface.json"):
        interface_path_org: Path = working_dir / "assets" / interface_filename
        if not interface_path_org.is_file():
            continue

        interface_path_new: Path = (
            install_path / "interface.json"
        )  # GUI 只能识别到 .json

        shutil.copy2(interface_path_org, interface_path_new)
        if not interface_path_new.is_file():
            raise RuntimeError(
                f'复制失败: "{interface_path_org}" -> "{interface_path_new}"'
            )

        interface: dict = jsonc.loads(interface_path_new.read_text(encoding="utf-8"))

        interface["version"] = version
        interface["agent"] = resolve_agent_config(working_dir, os_name)

        interface_path_new.write_text(
            jsonc.dumps(interface, ensure_ascii=False, indent=3), encoding="utf-8"
        )


def install_chores() -> None:
    shutil.copy2(
        working_dir / "README.md",
        install_path,
    )
    shutil.copy2(
        working_dir / "LICENSE",
        install_path,
    )


def install_agent() -> None:
    install_path.mkdir(parents=True, exist_ok=True)

    if os_name == "win" and (working_dir / "dist" / "agent.exe").is_file():
        shutil.copy2(
            working_dir / "dist" / "agent.exe",
            install_path / "agent.exe",
        )
        return

    shutil.copytree(
        working_dir / "agent",
        install_path / "agent",
        dirs_exist_ok=True,
    )


if __name__ == "__main__":
    args: argparse.Namespace = parse_args()
    version: str = args.version
    os_name: str = args.os
    arch: str = args.arch
    gui: str | None = args.gui

    install_deps()
    install_resource()
    install_chores()
    install_agent()

    print(f"Install to {install_path} successfully.")
