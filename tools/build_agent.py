from __future__ import annotations

from pathlib import Path


def build_pyinstaller_args(root: Path | str | None = None) -> list[str]:
    project_root = (
        Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    )
    pyinstaller_dir = project_root / "build" / "pyinstaller"

    return [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name=agent",
        f"--paths={project_root}",
        f"--distpath={project_root / 'dist'}",
        f"--workpath={pyinstaller_dir}",
        f"--specpath={pyinstaller_dir}",
        "--collect-all=maa",
        "--collect-all=MaaAgentBinary",
        "--collect-submodules=music21",
        str(project_root / "tools" / "agent_entry.py"),
    ]


def main(argv: object | None = None) -> None:
    if argv is not None:
        raise ValueError("build_agent does not accept custom arguments")

    from PyInstaller.__main__ import run

    run(build_pyinstaller_args())


if __name__ == "__main__":
    main()
