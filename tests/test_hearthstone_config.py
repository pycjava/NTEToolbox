"""hscoach 配置持久化测试（打包成品的运行配置）。

验证（全部在临时目录/假环境变量，绝不碰真实 APPDATA 配置）：
- 无配置文件时返回默认值
- 保存/读取往返一致（含 friendly_player_id 的 int 类型）
- 配置文件损坏时回退默认值
- 优先级：命令行 > 环境变量 > 配置文件 > 默认值
- 显式传空 --api-key 不回退（强制不配置，入口据此退出）
"""

import logging
import tempfile
import unittest
from pathlib import Path

logging.disable(logging.WARNING)

from hscoach.config import (
    CoachConfig,
    effective_config,
    load_config,
    save_config,
)


class ConfigFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg_path = self.tmp / "config.json"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_defaults_when_no_file(self):
        cfg = load_config(self.cfg_path)
        self.assertEqual(cfg.api_key, "")
        self.assertEqual(cfg.model, "deepseek-chat")
        self.assertEqual(cfg.base_url, "https://api.deepseek.com/v1")
        self.assertIsNone(cfg.friendly_player_id)

    def test_save_load_roundtrip(self):
        cfg = CoachConfig(
            api_key="sk-test-123",
            model="deepseek-v4-flash",
            base_url="https://opencode.ai/zen/go/v1",
            friendly_player_id=2,
        )
        path = save_config(cfg, self.cfg_path)
        self.assertTrue(path.exists())
        loaded = load_config(self.cfg_path)
        self.assertEqual(loaded.api_key, "sk-test-123")
        self.assertEqual(loaded.model, "deepseek-v4-flash")
        self.assertEqual(loaded.base_url, "https://opencode.ai/zen/go/v1")
        self.assertEqual(loaded.friendly_player_id, 2)  # int 保持类型
        # 无残留临时文件
        self.assertEqual(list(self.tmp.glob("*.tmp")), [])

    def test_corrupt_file_falls_back_to_defaults(self):
        self.cfg_path.write_text("{不是合法json", encoding="utf-8")
        cfg = load_config(self.cfg_path)
        self.assertEqual(cfg.api_key, "")

    def test_non_object_file_falls_back_to_defaults(self):
        self.cfg_path.write_text('["list"]', encoding="utf-8")
        cfg = load_config(self.cfg_path)
        self.assertEqual(cfg.api_key, "")


class EffectiveConfigTest(unittest.TestCase):
    """优先级：命令行 > 环境变量 > 配置文件 > 默认值。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg_path = self.tmp / "config.json"
        save_config(
            CoachConfig(api_key="from-file", model="model-file", base_url="url-file"),
            self.cfg_path,
        )
        self._orig_env = __import__("os").environ.get("HSCOACH_CONFIG")
        __import__("os").environ["HSCOACH_CONFIG"] = str(self.cfg_path)

    def tearDown(self):
        import os
        import shutil

        if self._orig_env is None:
            os.environ.pop("HSCOACH_CONFIG", None)
        else:
            os.environ["HSCOACH_CONFIG"] = self._orig_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_env_beats_config_file(self):
        cfg = effective_config(
            cli_key=None,
            env={"DEEPSEEK_API_KEY": "from-env"},
        )
        self.assertEqual(cfg.api_key, "from-env")
        # model/base_url 仍来自配置文件
        self.assertEqual(cfg.model, "model-file")
        self.assertEqual(cfg.base_url, "url-file")

    def test_cli_beats_env(self):
        cfg = effective_config(
            cli_key="from-cli",
            env={"DEEPSEEK_API_KEY": "from-env"},
        )
        self.assertEqual(cfg.api_key, "from-cli")

    def test_explicit_empty_cli_is_respected(self):
        """显式传空 --api-key：不回退到环境变量/配置文件。"""
        cfg = effective_config(
            cli_key="",
            env={"DEEPSEEK_API_KEY": "from-env"},
        )
        self.assertEqual(cfg.api_key, "")

    def test_nothing_set_uses_defaults(self):
        cfg = effective_config(cli_key=None, env={})
        self.assertEqual(cfg.api_key, "from-file")  # 配置文件兜底
        cfg2 = effective_config(cli_key=None, env={})
        self.assertEqual(cfg2.model, "model-file")

    def test_friendly_player_id_precedence(self):
        save_config(
            CoachConfig(api_key="k", friendly_player_id=2),
            self.cfg_path,
        )
        self.assertEqual(effective_config(cli_key=None, env={}).friendly_player_id, 2)
        self.assertEqual(effective_config(cli_key="k", cli_friendly=1, env={}).friendly_player_id, 1)


if __name__ == "__main__":
    unittest.main()
