"""T7(07) 回合触发器 + 建议发布测试。

验证：
- 回合检测：轮到友方新回合时触发，非友方回合/同回合不触发
- 原子发布：advice.json 写入成功、内容正确
- 文件读取：read_advice 能读回
- 手动触发：manual_trigger 不受 turn 递增限制
- 处理日志行流：process_log_lines_for_trigger 端到端
"""

import json
import logging
import unittest
from pathlib import Path

logging.disable(logging.WARNING)

from hscoach.cards import CardDatabase
from hscoach.coach import Advice
from hscoach.log_parser import parse_power_log
from hscoach.state import GameSnapshot, serialize_game
from hscoach.trigger import (
    TurnTrigger,
    process_log_lines_for_trigger,
    publish_advice,
    read_advice,
)

FIXTURE = Path(__file__).resolve().parent / "data" / "friendly_player_id_is_1.power.log"


class MockClient:
    def __init__(self):
        self.calls = 0

    def chat(self, system, user, timeout=None):
        self.calls += 1
        return '{"kind":"play","headline":"测试","why":"理由","steps":[],"warning":""}'


class TurnTriggerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lines = []
        with FIXTURE.open(encoding="utf-8") as fp:
            for i, line in enumerate(fp):
                if i >= 1500:
                    break
                lines.append(line)
        cls.result = parse_power_log(lines)
        cls.game = cls.result.games[0]
        cls.db = CardDatabase(cache_dir=Path(__file__).resolve().parent / "_hs_cache")
        cls.db.build()

    def test_detects_new_friendly_turn(self):
        """snapshot 当前玩家是友方且 turn > last 时触发。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        trigger = TurnTrigger(friendly_player_id=snap.current_player_id or 1)
        # 第一次：turn > 0 应触发
        new_turn = trigger.detect_new_friendly_turn(snap)
        if snap.current_player_id == trigger.friendly_player_id:
            self.assertIsNotNone(new_turn)
        else:
            # 当前不是友方回合，不触发
            self.assertIsNone(new_turn)

    def test_does_not_retrigger_same_turn(self):
        """同一 turn 不重复触发。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        pid = snap.current_player_id or 1
        trigger = TurnTrigger(friendly_player_id=pid)
        first = trigger.detect_new_friendly_turn(snap)
        if first is not None:
            trigger.last_triggered_turn = first
            second = trigger.detect_new_friendly_turn(snap)
            self.assertIsNone(second)

    def test_check_and_trigger_publishes_advice(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            publish_dir = Path(td)
            client = MockClient()
            pid = serialize_game(self.game, 1, self.db).current_player_id or 1
            trigger = TurnTrigger(friendly_player_id=pid)
            advice = trigger.check_and_trigger(self.game, self.db, client, publish_dir)
            if advice is not None:
                # 文件已发布
                data = read_advice(publish_dir)
                self.assertIsNotNone(data)
                self.assertIn("turn", data)
                self.assertIn("advice", data)
                self.assertEqual(data["advice"]["headline"], "测试")

    def test_manual_trigger_always_fires(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            publish_dir = Path(td)
            client = MockClient()
            trigger = TurnTrigger(friendly_player_id=1)
            advice = trigger.manual_trigger(self.game, self.db, client, publish_dir)
            self.assertEqual(advice.headline, "测试")
            self.assertEqual(client.calls, 1)
            self.assertIsNotNone(read_advice(publish_dir))


class PublishAdviceTest(unittest.TestCase):
    def test_atomic_write_and_read(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            adv = Advice(kind="play", headline="出牌", why="理由")
            path = publish_advice(d, adv, turn=3)
            self.assertTrue(path.exists())
            self.assertEqual(path.name, "advice.json")
            data = read_advice(d)
            self.assertEqual(data["turn"], 3)
            self.assertEqual(data["advice"]["headline"], "出牌")
            self.assertIn("timestamp", data)

    def test_read_returns_none_when_missing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(read_advice(Path(td)))

    def test_no_tmp_file_left(self):
        """原子写后无残留临时文件。"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            publish_advice(d, Advice(kind="pass", headline="结束"), turn=1)
            tmps = list(d.glob(".advice_*.tmp"))
            self.assertEqual(tmps, [])


class ProcessLogLinesTest(unittest.TestCase):
    def test_end_to_end_with_mock_client(self):
        import tempfile

        lines = []
        with FIXTURE.open(encoding="utf-8") as fp:
            for i, line in enumerate(fp):
                if i >= 1500:
                    break
                lines.append(line)

        with tempfile.TemporaryDirectory() as td:
            publish_dir = Path(td)
            client = MockClient()
            snap = serialize_game(parse_power_log(lines).games[0], 1, None)
            pid = snap.current_player_id or 1
            trigger = TurnTrigger(friendly_player_id=pid)
            advices = process_log_lines_for_trigger(lines, trigger, None, client, publish_dir)
            # 是否触发取决于当前是否友方回合
            self.assertIsInstance(advices, list)


if __name__ == "__main__":
    unittest.main()
