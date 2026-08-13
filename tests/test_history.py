"""T-H1 对局结果与战绩统计测试（竞品对齐：HDT/盒子的对局记录/胜率）。

游戏结束时 Power.log 在 GameEntity 上写 tag=PLAYSTATE value=4/5/6
（WON/LOST/TIED，本地玩家视角）。检测器从原始日志行正则提取；结果
追加 history.jsonl + 聚合 stats.json 供前端盒子显示战绩。
"""

import json
import logging
import tempfile
import unittest
from pathlib import Path

logging.disable(logging.WARNING)

from hscoach.history import (
    HISTORY_FILENAME,
    STATS_FILENAME,
    GameResultDetector,
    record_result,
)
from tests._helpers import read_fixture_lines

logger = logging.getLogger(__name__)


def _playstate_lines(entity: str, value: str) -> list[str]:
    """构造真实 Power.log 形态的 PLAYSTATE 行（玩家实体 + 枚举名）。"""
    return [
        "GameState.DebugPrintPower() -     TAG_CHANGE "
        f"Entity={entity} tag=PLAYSTATE value={value}"
    ]


class GameResultDetectorTest(unittest.TestCase):
    """PLAYSTATE 终局检测（真实日志格式）。

    真实 Power.log 把 PLAYSTATE 写在【玩家实体】（PlayerOne/PlayerTwo 或
    数字 2/3），值是【枚举名】WON/LOST/TIED（非数字 4/5/6），且双方各写
    一次。检测器必须按 friendly_player_id 取【友方】实体的结果。
    """

    def test_real_format_win_attributed_to_friendly(self):
        det = GameResultDetector(friendly_player_id=1)
        out = det.feed(_playstate_lines("PlayerOne", "WON") + _playstate_lines("PlayerTwo", "LOST"))
        self.assertEqual(out, ["win"])

    def test_real_format_loss_attributed_to_friendly(self):
        det = GameResultDetector(friendly_player_id=1)
        out = det.feed(_playstate_lines("PlayerOne", "LOST") + _playstate_lines("PlayerTwo", "WON"))
        self.assertEqual(out, ["loss"])

    def test_result_follows_friendly_id_swap(self):
        """friendly=2 时取 PlayerTwo 的结果（修复前取首个命中会记反）。"""
        det = GameResultDetector(friendly_player_id=2)
        out = det.feed(_playstate_lines("PlayerOne", "LOST") + _playstate_lines("PlayerTwo", "WON"))
        self.assertEqual(out, ["win"])

    def test_numeric_entity_resolves_via_protocol_constant(self):
        """数字实体：Entity=2→玩家1（协议常量 EntityID 2=先手）。"""
        det1 = GameResultDetector(friendly_player_id=1)
        self.assertEqual(det1.feed(_playstate_lines("2", "WON")), ["win"])
        # entity 3 = 玩家2 = 对手 → 友方无终局行 → 空
        det2 = GameResultDetector(friendly_player_id=1)
        self.assertEqual(det2.feed(_playstate_lines("3", "WON")), [])

    def test_ignores_non_terminal_playstates(self):
        """PLAYING/WINNING/LOSING 是进行中状态，不是终局。"""
        det = GameResultDetector(friendly_player_id=1)
        out = det.feed(
            _playstate_lines("PlayerOne", "PLAYING")
            + _playstate_lines("PlayerOne", "WINNING")
            + _playstate_lines("PlayerOne", "LOSING")
        )
        self.assertEqual(out, [])

    def test_ignores_when_only_opponent_has_terminal_line(self):
        det = GameResultDetector(friendly_player_id=1)
        self.assertEqual(det.feed(_playstate_lines("PlayerTwo", "WON")), [])

    def test_single_fire_per_game(self):
        det = GameResultDetector(friendly_player_id=1)
        self.assertEqual(det.feed(_playstate_lines("PlayerOne", "WON")), ["win"])
        self.assertEqual(det.feed(_playstate_lines("PlayerOne", "WON")), [])

    def test_create_game_resets_for_next_match(self):
        det = GameResultDetector(friendly_player_id=1)
        det.feed(_playstate_lines("PlayerOne", "LOST"))
        out = det.feed(["GameState... CREATE_GAME - ..."] + _playstate_lines("PlayerOne", "WON"))
        self.assertEqual(out, ["win"])

    def test_reset_method(self):
        det = GameResultDetector(friendly_player_id=1)
        det.feed(_playstate_lines("PlayerOne", "WON"))
        det.reset()
        self.assertEqual(det.feed(_playstate_lines("PlayerOne", "WON")), ["win"])


class RealFixtureGameResultTest(unittest.TestCase):
    """真实 fixture 端到端回归：PlayerOne（玩家1=friendly）= LOST。"""

    def test_detects_friendly_loss_from_real_log(self):
        det = GameResultDetector(friendly_player_id=1)
        results = det.feed(read_fixture_lines())
        self.assertEqual(results, ["loss"])


class RecordResultTest(unittest.TestCase):
    """history.jsonl 追加 + stats.json 聚合。"""

    def test_first_win(self):
        with tempfile.TemporaryDirectory() as td:
            stats = record_result(Path(td), "win", "MAGE", "WARLOCK", turns=12)
            self.assertEqual(stats["total"], 1)
            self.assertEqual(stats["wins"], 1)
            self.assertEqual(stats["losses"], 0)
            self.assertEqual(stats["winrate_pct"], 100.0)

    def test_aggregates_winrate(self):
        with tempfile.TemporaryDirectory() as td:
            record_result(Path(td), "win", "MAGE", "WARLOCK", turns=10)
            stats = record_result(Path(td), "loss", "MAGE", "HUNTER", turns=8)
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["wins"], 1)
            self.assertEqual(stats["losses"], 1)
            self.assertEqual(stats["winrate_pct"], 50.0)

    def test_tie_counted_separately(self):
        with tempfile.TemporaryDirectory() as td:
            record_result(Path(td), "tie", "MAGE", "MAGE", turns=20)
            stats = record_result(Path(td), "win", "MAGE", "ROGUE", turns=9)
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["ties"], 1)
            self.assertEqual(stats["winrate_pct"], 50.0)

    def test_history_lines_are_json_with_required_fields(self):
        with tempfile.TemporaryDirectory() as td:
            record_result(Path(td), "win", "MAGE", "WARLOCK", turns=12)
            lines = (Path(td) / HISTORY_FILENAME).read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry["result"], "win")
            self.assertEqual(entry["friendly_class"], "MAGE")
            self.assertEqual(entry["opponent_class"], "WARLOCK")
            self.assertEqual(entry["turns"], 12)
            self.assertIn("timestamp", entry)

    def test_stats_file_written(self):
        with tempfile.TemporaryDirectory() as td:
            record_result(Path(td), "win", "MAGE", "WARLOCK", turns=12)
            path = Path(td) / STATS_FILENAME
            self.assertTrue(path.exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["total"], 1)

    def test_by_class_aggregation(self):
        with tempfile.TemporaryDirectory() as td:
            record_result(Path(td), "win", "MAGE", "WARLOCK", turns=10)
            record_result(Path(td), "loss", "MAGE", "HUNTER", turns=8)
            stats = record_result(Path(td), "win", "HUNTER", "MAGE", turns=7)
            self.assertEqual(stats["by_class"]["MAGE"]["wins"], 1)
            self.assertEqual(stats["by_class"]["MAGE"]["losses"], 1)
            self.assertEqual(stats["by_class"]["HUNTER"]["wins"], 1)

    def test_recent_kept_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(15):
                record_result(Path(td), "win" if i % 2 == 0 else "loss", "MAGE", "WARLOCK", turns=i + 1)
            stats = json.loads((Path(td) / STATS_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(stats["total"], 15)
            self.assertLessEqual(len(stats["recent"]), 10)


if __name__ == "__main__":
    unittest.main()
