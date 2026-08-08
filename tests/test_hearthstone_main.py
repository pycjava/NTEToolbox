"""入口（__main__）可分离逻辑测试。

验证：
- main 无 API key 时返回退出码 2（显式传空串不弹输入框，脚本/测试友好）
- calibrate_friendly_player：从解析结果自动校准友方玩家 id
  （hslog FriendlyPlayerExporter 优先，手牌 CardID 启发式兜底）
- _ClientHolder：LLM 客户端容器支持热切换（设置里改模型/地址即时生效）
"""

import logging
import unittest

logging.disable(logging.WARNING)

from hscoach.__main__ import _ClientHolder, calibrate_friendly_player, main
from hscoach.log_parser import parse_power_log
from tests._helpers import read_fixture_lines


class MainEntryTest(unittest.TestCase):
    def test_missing_api_key_returns_exit_code_2(self):
        # 显式传空串 = 明确不配置 → 直接报错退出，不弹输入框
        self.assertEqual(main(["--api-key", ""]), 2)

    def test_explicit_empty_key_ignores_env(self):
        """显式空 --api-key 不回退到环境变量/配置文件。"""
        import os

        old = os.environ.get("DEEPSEEK_API_KEY")
        os.environ["DEEPSEEK_API_KEY"] = "sk-from-env"
        try:
            self.assertEqual(main(["--api-key", ""]), 2)
        finally:
            if old is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = old


class ClientHolderTest(unittest.TestCase):
    def test_delegates_and_hot_swaps(self):
        """设置里改完模型/地址后热切换：后续 chat 走新客户端。"""

        class FakeClient:
            def __init__(self, tag):
                self.tag = tag

            def chat(self, system, user, timeout=None):
                return f"reply-{self.tag}"

        holder = _ClientHolder(FakeClient("a"))
        self.assertEqual(holder.chat("s", "u"), "reply-a")
        holder.client = FakeClient("b")  # 热切换
        self.assertEqual(holder.chat("s", "u"), "reply-b")


class CalibrateFriendlyPlayerTest(unittest.TestCase):
    def test_calibrates_player_1_from_fixture(self):
        """真实对局（友方=1）能自动校准出 1（D9 防线核心）。"""
        result = parse_power_log(read_fixture_lines(4000))
        self.assertEqual(calibrate_friendly_player(result), 1)

    def test_returns_none_without_games(self):
        from hscoach.log_parser import ParseResult

        self.assertIsNone(calibrate_friendly_player(ParseResult()))

    def test_returns_none_when_hands_empty(self):
        """开局调度阶段无法判断 → None（调用方沿用现有 id）。"""
        result = parse_power_log(read_fixture_lines(1500))
        self.assertIsNone(calibrate_friendly_player(result))


if __name__ == "__main__":
    unittest.main()
