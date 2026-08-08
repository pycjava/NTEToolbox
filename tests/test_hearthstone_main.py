"""入口（__main__）可分离逻辑测试。

验证：
- main 无 API key 时返回退出码 2（不联网、不启动 UI）
- calibrate_friendly_player：从解析结果自动校准友方玩家 id
  （hslog FriendlyPlayerExporter 优先，手牌 CardID 启发式兜底）
"""

import logging
import unittest

logging.disable(logging.WARNING)

from hscoach.__main__ import calibrate_friendly_player, main
from hscoach.log_parser import parse_power_log
from tests._helpers import read_fixture_lines


class MainEntryTest(unittest.TestCase):
    def test_missing_api_key_returns_exit_code_2(self):
        self.assertEqual(main(["--api-key", ""]), 2)


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
