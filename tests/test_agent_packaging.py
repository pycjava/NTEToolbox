import ast
import importlib.util
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_tool_module(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"failed to load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(path.parent))


def strip_jsonc_comments(text: str) -> str:
    validate_schema = load_tool_module(
        "validate_schema", ROOT / "tools" / "validate_schema.py"
    )
    return validate_schema.strip_jsonc_comments(text)


class AgentPackagingTest(unittest.TestCase):
    def test_nsis_script_packages_install_directory_recursively(self):
        script = (ROOT / "installer" / "NTEToolbox.nsi").read_text(encoding="utf-8")

        self.assertIn('!define INSTALL_SOURCE "..\\install"', script)
        self.assertIn('SetOutPath "$INSTDIR"', script)
        self.assertIn('File /r /x "debug" /x "logs" /x "temp" "${INSTALL_SOURCE}\\*.*"', script)

    def test_nsis_script_installs_missing_dotnet_and_vc_runtime(self):
        script = (ROOT / "installer" / "NTEToolbox.nsi").read_text(encoding="utf-8")

        self.assertIn("Function EnsureDotNetRuntime", script)
        self.assertIn("Function EnsureVCRedist", script)
        self.assertIn('Microsoft.WindowsDesktop.App', script)
        self.assertIn('VisualStudio\\14.0\\VC\\Runtimes', script)
        self.assertIn('powershell.exe', script)
        self.assertIn('Invoke-WebRequest', script)
        self.assertIn('/passive /norestart', script)

    def test_nsis_script_creates_desktop_shortcut_to_configured_gui(self):
        script = (ROOT / "installer" / "NTEToolbox.nsi").read_text(encoding="utf-8")

        self.assertIn('!define GUI_EXE "MFAAvalonia.exe"', script)
        self.assertIn('IfFileExists "$INSTDIR\\${GUI_EXE}"', script)
        self.assertIn(
            'CreateShortcut "$DESKTOP\\NTEToolbox.lnk" "$INSTDIR\\${GUI_EXE}"',
            script,
        )

    def test_nsis_build_script_can_select_mfaa_or_mxu_shortcut_target(self):
        script = (ROOT / "tools" / "build_nsis.ps1").read_text(encoding="utf-8")

        self.assertIn("[ValidateSet('mfaa', 'mxu')]", script)
        self.assertIn('"mfaa" { "MFAAvalonia.exe" }', script)
        self.assertIn('"mxu" { "mxu.exe" }', script)
        self.assertIn('/DGUI_EXE=$guiExe', script)
        self.assertIn("makensis", script)

    def test_install_build_script_recreates_install_directory(self):
        script = (ROOT / "tools" / "build_install.ps1").read_text(encoding="utf-8")

        self.assertIn("[ValidateSet('mfaa', 'mxu')]", script)
        self.assertIn("function Invoke-Step", script)
        self.assertIn("function Assert-SafeInstallDir", script)
        self.assertIn("function Clear-IntermediateArtifacts", script)
        self.assertIn("$LASTEXITCODE", script)
        self.assertIn('Join-Path $repoRoot "build\\pyinstaller"', script)
        self.assertIn('Join-Path $repoRoot "dist\\agent.exe"', script)
        self.assertIn('Get-ChildItem -LiteralPath $repoRoot -Filter "*.egg-info"', script)
        self.assertIn("finally", script)
        self.assertIn("Remove-Item -Recurse -Force", script)
        self.assertIn("Copy-Item -Recurse -Force", script)
        self.assertIn(
            'Invoke-Step "python" @("-m", "pip", "install", "-e", ".", "pyinstaller")',
            script,
        )
        self.assertIn('Invoke-Step "python" @(".\\tools\\build_agent.py")', script)
        self.assertIn(
            'Invoke-Step "python" @("-m", "pip", "install", "-r", ".\\tools\\requirements.txt")',
            script,
        )
        self.assertIn('Invoke-Step "python" @(".\\tools\\install.py"', script)
        self.assertIn('"--os", "win", "--arch", "x86_64"', script)
        self.assertIn('"--gui", $Gui', script)
        self.assertIn('"--install-dir", $InstallDir', script)
        self.assertIn("Assert-SafeInstallDir -Path $InstallDir", script)

    def test_install_script_accepts_install_dir_override(self):
        install = load_tool_module("install", ROOT / "tools" / "install.py")
        install_dir = ROOT / "custom-install"

        with patch.object(
            sys,
            "argv",
            [
                "install.py",
                "--version",
                "v1.9.0",
                "--os",
                "win",
                "--arch",
                "x86_64",
                "--gui",
                "mfaa",
                "--install-dir",
                str(install_dir),
            ],
        ):
            args = install.parse_args()

        self.assertEqual(args.install_dir, str(install_dir))

    def test_build_agent_uses_packaged_entry_and_agent_name(self):
        build_agent = load_tool_module("build_agent", ROOT / "tools" / "build_agent.py")

        args = build_agent.build_pyinstaller_args(ROOT)

        self.assertIn("--onefile", args)
        self.assertIn("--clean", args)
        self.assertIn("--name=agent", args)
        self.assertIn(f"--paths={ROOT}", args)
        self.assertIn("--collect-all=MaaAgentBinary", args)
        self.assertNotIn("--collect-all=maaagentbinary", args)
        self.assertIn(str(ROOT / "tools" / "agent_entry.py"), args)

    def test_tauri_config_bundles_prepared_maa_runtime_resources(self):
        tauri_config = json.loads(
            (ROOT / "client" / "src-tauri" / "tauri.conf.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            tauri_config["bundle"]["resources"],
            {
                "gen/maafw/": "maafw/",
            },
        )

    def test_tauri_before_build_prepares_maa_runtime_resources(self):
        client_package = json.loads(
            (ROOT / "client" / "package.json").read_text(encoding="utf-8")
        )
        tauri_config = json.loads(
            (ROOT / "client" / "src-tauri" / "tauri.conf.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            client_package["scripts"]["prepare:maafw"],
            "node scripts/prepare-maafw.mjs",
        )
        self.assertIn(
            "pnpm prepare:maafw",
            tauri_config["build"]["beforeBuildCommand"],
        )
        self.assertTrue((ROOT / "client" / "scripts" / "prepare-maafw.mjs").is_file())

    def test_tauri_build_script_builds_agent_for_standalone_runtime(self):
        script = (ROOT / "tools" / "build_tauri.ps1").read_text(encoding="utf-8")

        self.assertIn('Join-Path $repoRoot "dist\\agent.exe"', script)
        self.assertIn(
            'Invoke-Step "python" @("-m", "pip", "install", "-e", ".", "pyinstaller")',
            script,
        )
        self.assertIn('Invoke-Step "python" @(".\\tools\\build_agent.py")', script)

    def test_install_agent_copies_windows_exe(self):
        install = load_tool_module("install", ROOT / "tools" / "install.py")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir()
            (dist / "agent.exe").write_bytes(b"agent exe")

            install.working_dir = root
            install.install_path = root / "install"
            install.os_name = "win"

            install.install_agent()

            self.assertEqual((root / "install" / "agent.exe").read_bytes(), b"agent exe")
            self.assertFalse((root / "install" / "agent").exists())

    def test_install_agent_falls_back_to_source_when_windows_exe_is_missing(self):
        install = load_tool_module("install", ROOT / "tools" / "install.py")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_agent = root / "agent"
            source_agent.mkdir()
            (source_agent / "__main__.py").write_text("print('agent')", encoding="utf-8")

            install.working_dir = root
            install.install_path = root / "install"
            install.os_name = "win"

            install.install_agent()

            self.assertTrue((root / "install" / "agent" / "__main__.py").is_file())
            self.assertFalse((root / "install" / "agent.exe").exists())

    def test_resolve_agent_config_uses_exe_only_when_windows_exe_exists(self):
        install = load_tool_module("install", ROOT / "tools" / "install.py")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            self.assertEqual(
                install.resolve_agent_config(root, "win"),
                {"child_exec": "python", "child_args": ["-u", "-m", "agent"]},
            )
            self.assertEqual(
                install.resolve_agent_config(root, "linux"),
                {"child_exec": "python", "child_args": ["-u", "-m", "agent"]},
            )

            dist = root / "dist"
            dist.mkdir()
            (dist / "agent.exe").write_bytes(b"agent exe")

            self.assertEqual(
                install.resolve_agent_config(root, "win"),
                {"child_exec": "./agent.exe", "child_args": []},
            )

    def test_workflow_builds_and_downloads_windows_agent_exe(self):
        workflow = (ROOT / ".github" / "workflows" / "install.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("build-agent-windows:", workflow)
        self.assertIn("python tools/build_agent.py", workflow)
        self.assertIn("internal-agent-win-x86_64", workflow)
        self.assertNotIn("NTEToolbox-agent-win-x86_64", workflow)
        self.assertIn("pattern: NTEToolbox-*", workflow)

    def test_source_interface_uses_python_agent_for_development(self):
        interface = json.loads(
            strip_jsonc_comments(
                (ROOT / "assets" / "interface.jsonc").read_text(encoding="utf-8")
            )
        )

        self.assertEqual(interface["agent"]["child_exec"], "python")
        self.assertEqual(interface["agent"].get("child_args", []), ["-u", "-m", "agent"])

    def test_package_metadata_reads_version_from_lightweight_module(self):
        pyproject = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(
            pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "agent._version.__version__",
        )

        version_module = ast.parse(
            (ROOT / "agent" / "_version.py").read_text(encoding="utf-8")
        )
        assignments = [
            node
            for node in version_module.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in node.targets
            )
        ]
        self.assertEqual(len(assignments), 1)
        self.assertIsInstance(assignments[0].value, ast.Constant)
        self.assertIsInstance(assignments[0].value.value, str)

        interface = json.loads(
            strip_jsonc_comments(
                (ROOT / "assets" / "interface.jsonc").read_text(encoding="utf-8")
            )
        )
        self.assertEqual(assignments[0].value.value, interface["version"])


if __name__ == "__main__":
    unittest.main()
