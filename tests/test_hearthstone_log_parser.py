"""T2(04) 日志解析测试。

验证（用真实 HearthSim 测试 fixture）：
- 真实 Power.log 能解析出 Game，含双方玩家
- 坏行被跳过、计数，不让整个解析崩
- 多局文件按 CREATE_GAME 边界正确切分
- 解析出的实体含 CardID（SHOW_ENTITY 揭示后）
"""

import logging
import unittest
from pathlib import Path

# 抑制 hslog 解析真实日志时产生的大量 META_DATA WARNING 噪音
logging.disable(logging.WARNING)

from hearthstone.enums import GameTag, Zone
from hscoach.log_parser import parse_power_log, parse_power_log_file

FIXTURE = Path(__file__).resolve().parent / "data" / "friendly_player_id_is_1.power.log"


class LogParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 限制行数加速测试：前 1500 行已含完整开局 + 多回合
        cls.head_lines = cls._read_head(FIXTURE, 1500)
        # 解析一次，所有测试复用（解析 1500 行约需数秒）
        cls.result = parse_power_log(cls.head_lines)
        cls.game = cls.result.games[0] if cls.result.games else None

    @staticmethod
    def _read_head(path: Path, n: int) -> list[str]:
        with path.open(encoding="utf-8") as fp:
            return [next(fp, "") for _ in range(n)]

    def test_parses_real_log_into_game(self):
        result = parse_power_log(self.head_lines)
        self.assertGreaterEqual(len(result.games), 1)
        game = result.games[0]
        self.assertEqual(len(game.players), 2)

    def test_game_has_entities_with_card_ids(self):
        game = self.game
        # game.entities 可能是 generator，物化它
        entities = list(game.entities)
        self.assertGreater(len(entities), 0)
        # 至少有一些实体带 card_id（SHOW_ENTITY 揭示后）
        with_card_id = [e for e in entities if getattr(e, "card_id", None)]
        self.assertGreater(len(with_card_id), 0)

    def test_bad_lines_are_skipped_not_fatal(self):
        """在真实日志里掺入垃圾行，解析不应崩溃，坏行被计数。"""
        polluted = list(self.head_lines)
        # 插入几行无法解析的垃圾
        polluted.insert(100, "这不是一行合法的日志")
        polluted.insert(200, "")
        polluted.insert(300, "garbage line without timestamp")
        result = parse_power_log(polluted)
        self.assertGreaterEqual(result.skipped_lines, 2)  # 至少 2 行垃圾被跳过
        self.assertGreaterEqual(len(result.games), 1)  # 主体仍解析成功

    def test_create_game_boundary_splits_games(self):
        """两局日志（重复 fixture 两次，中间隔空行）应解析出两个 game。"""
        two_games = list(self.head_lines) + [""] + list(self.head_lines)
        result = parse_power_log(two_games)
        self.assertGreaterEqual(len(result.games), 2)

    def test_parse_file_helper(self):
        result = parse_power_log_file(FIXTURE)
        self.assertGreaterEqual(len(result.games), 1)

    def test_in_zone_finds_zone_entities(self):
        """解析出的 Game 能用 in_zone 查到至少一个区域的实体。"""
        game = self.game
        # 开局早期手牌可能尚未揭示，检查手牌+场上+牌库至少有实体
        found_any = False
        for zenum in (Zone.HAND, Zone.PLAY, Zone.DECK):
            ents = list(game.in_zone(zenum))
            if ents:
                found_any = True
                # 实体应有 controller tag（区分玩家）
                self.assertTrue(any(GameTag.CONTROLLER in e.tags for e in ents))
                break
        self.assertTrue(found_any, "前 1500 行应至少在 HAND/PLAY/DECK 某区有实体")


if __name__ == "__main__":
    unittest.main()
