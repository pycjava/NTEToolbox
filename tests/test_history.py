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

logger = logging.getLogger(__name__)


class GameResultDetectorTest(unittest.TestCase):
    """PLAYSTATE 检测：只认 GameEntity 上的 4/5/6，每局只记一次。"""

    def test_detects_win(self):
        det = GameResultDetector()
        self.assertEqual(
            det.feed(["TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=4"]),
            ["win"],
        )

    def test_detects_loss_and_tie(self):
        det = GameResultDetector()
        self.assertEqual(det.feed(["TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=5"]), ["loss"])
        det.reset()  # 下一局
        self.assertEqual(det.feed(["TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=6"]), ["tie"])

    def test_ignores_playing_states(self):
        """对局中的 1/2/3（进行中/即将胜/即将负）不是终局结果。"""
        det = GameResultDetector()
        self.assertEqual(
            det.feed([
                "TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=1",
                "TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=2",
                "TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=3",
            ]),
            [],
        )

    def test_ignores_non_game_entity_lines(self):
        """其他实体上的 PLAYSTATE（如玩家实体）不是对局结果。"""
        det = GameResultDetector()
        self.assertEqual(
            det.feed(["TAG_CHANGE Entity=3 tag=PLAYSTATE value=4"]),
            [],
        )

    def test_single_fire_per_game(self):
        """同一局重复写 PLAYSTATE 只记一次。"""
        det = GameResultDetector()
        self.assertEqual(det.feed(["TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=4"]), ["win"])
        self.assertEqual(det.feed(["TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=4"]), [])

    def test_create_game_resets_for_next_match(self):
        """CREATE_GAME 开启新对局 → 下一局结果可再次触发。"""
        det = GameResultDetector()
        lines = [
            "TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=4",
            "CREATE_GAME",
            "TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=5",
        ]
        self.assertEqual(det.feed(lines), ["win", "loss"])

    def test_reset_method(self):
        det = GameResultDetector()
        det.feed(["TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=4"])
        det.reset()
        self.assertEqual(det.feed(["TAG_CHANGE Entity=GameEntity tag=PLAYSTATE value=4"]), ["win"])


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
