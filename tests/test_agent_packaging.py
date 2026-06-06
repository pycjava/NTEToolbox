import ast
import importlib.util
import json
import sys
import tomllib
import unittest
from pathlib import Path

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
