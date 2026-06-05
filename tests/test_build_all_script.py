import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "build_all.ps1"


def powershell_exe() -> str:
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if exe is None:
        pytest.skip("PowerShell is not available")
    return exe


def run_build_all_plan(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            powershell_exe(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-PlanOnly",
            *args,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def test_build_all_can_plan_tauri_only():
    result = run_build_all_plan("-LegacyGui", "none")

    assert result.returncode == 0, result.stdout
    assert "build_tauri.ps1" in result.stdout
    assert "build_install.ps1" not in result.stdout
    assert "build_nsis.ps1" not in result.stdout


def test_build_all_can_plan_mfaa_install_and_nsis(tmp_path: Path):
    mfa_source = tmp_path / "MFA"
    mfa_source.mkdir()
    (mfa_source / "MFAAvalonia.exe").write_bytes(b"fake exe")

    result = run_build_all_plan(
        "-SkipTauri",
        "-LegacyGui",
        "mfaa",
        "-MfaSourceDir",
        str(mfa_source),
        "-Version",
        "v9.9.9",
        "-InstallDir",
        str(tmp_path / "install"),
        "-InstallerOutputDir",
        str(tmp_path / "installer"),
        "-Makensis",
        "custom-makensis",
    )

    assert result.returncode == 0, result.stdout
    assert "build_tauri.ps1" not in result.stdout
    assert "build_install.ps1" in result.stdout
    assert "build_nsis.ps1" in result.stdout
    assert "-Gui mfaa" in result.stdout
    assert "-Version v9.9.9" in result.stdout
    assert "-Makensis custom-makensis" in result.stdout


def test_build_all_fails_when_requested_legacy_gui_is_missing(tmp_path: Path):
    missing_source = tmp_path / "missing-mfa"

    result = run_build_all_plan(
        "-SkipTauri",
        "-LegacyGui",
        "mfaa",
        "-MfaSourceDir",
        str(missing_source),
    )

    assert result.returncode != 0
    assert "Selected legacy GUI source is missing" in result.stdout
    assert "MFAAvalonia.exe" in result.stdout
