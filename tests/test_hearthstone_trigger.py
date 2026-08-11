"""T7(07) 回合触发器 + 建议发布测试。

验证：
- 回合检测：轮到友方新回合时触发，非友方回合/同回合不触发
- 检测器 CURRENT_PLAYER 解析：名字形态（PlayerOne/PlayerTwo）与数字形态
  （Entity=3）都能正确映射到玩家 id；value=0 的置零行被忽略
- 用真实 fixture 全量验证：friendly=1 触发双数回合、friendly=2 触发单数
  回合（fixture 语义：单数回合 PlayerTwo 当前、双数回合 PlayerOne 当前）
- 原子发布：advice.json 写入成功、内容正确、无残留临时文件
- 手动触发：manual_trigger 不受 turn 递增限制
- LLM 失败降级：check_and_trigger 用上一回合建议兜底（spec 超时降级）
"""

import json
import logging
import unittest
from pathlib import Path

import httpx

logging.disable(logging.WARNING)

from hscoach.coach import Advice
from hscoach.log_parser import parse_power_log
from hscoach.state import serialize_game
from hscoach.trigger import (
    GAME_STATE_FILENAME,
    IncrementalTurnDetector,
    TurnTrigger,
    publish_advice,
    publish_game_state,
)
from tests._helpers import read_fixture_lines

# 真实 fixture 的行语义（已逐行核对）：
#   turn 1  = line 3188，当前 PlayerTwo（玩家2，Entity=3 数字形态）
#   turn 2  = line 3560，当前 PlayerOne（玩家1，名字形态）
#   单数回合 PlayerTwo 当前，双数回合 PlayerOne 当前，直到 turn 15
#   CREATE_GAME 块声明：EntityID=2↔PlayerID=1、EntityID=3↔PlayerID=2


class MockClient:
    def __init__(self):
        self.calls = 0

    def chat(self, system, user, timeout=None):
        self.calls += 1
        return '{"kind":"play","headline":"测试","why":"理由","steps":[],"warning":""}'


class TurnTriggerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = parse_power_log(read_fixture_lines(4000))  # turn 4，当前玩家 1
        cls.game = result.games[0]

    def test_detects_new_friendly_turn(self):
        """snapshot 当前玩家是友方且 turn > last 时触发。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=None)
        trigger = TurnTrigger(friendly_player_id=snap.current_player_id or 1)
        new_turn = trigger.detect_new_friendly_turn(snap)
        if snap.current_player_id == trigger.friendly_player_id:
            self.assertIsNotNone(new_turn)
        else:
            # 当前不是友方回合，不触发
            self.assertIsNone(new_turn)

    def test_does_not_retrigger_same_turn(self):
        """同一 turn 不重复触发。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=None)
        pid = snap.current_player_id or 1
        trigger = TurnTrigger(friendly_player_id=pid)
        first = trigger.detect_new_friendly_turn(snap)
        if first is not None:
            trigger.last_triggered_turn = first
            self.assertIsNone(trigger.detect_new_friendly_turn(snap))

    def test_check_and_trigger_publishes_advice(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            publish_dir = Path(td)
            client = MockClient()
            pid = serialize_game(self.game, 1, None).current_player_id or 1
            trigger = TurnTrigger(friendly_player_id=pid)
            advice = trigger.check_and_trigger(self.game, None, client, publish_dir)
            if advice is not None:
                data = json.loads(
                    (publish_dir / "advice.json").read_text(encoding="utf-8")
                )
                self.assertIn("turn", data)
                self.assertIn("advice", data)
                self.assertEqual(data["advice"]["headline"], "测试")

    def test_manual_trigger_always_fires(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            publish_dir = Path(td)
            client = MockClient()
            trigger = TurnTrigger(friendly_player_id=1)
            advice = trigger.manual_trigger(self.game, None, client, publish_dir)
            self.assertEqual(advice.headline, "测试")
            self.assertEqual(client.calls, 1)
            self.assertTrue((publish_dir / "advice.json").exists())


class PublishAdviceTest(unittest.TestCase):
    def test_atomic_write_and_read(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            adv = Advice(kind="play", headline="出牌", why="理由")
            path = publish_advice(d, adv, turn=3)
            self.assertTrue(path.exists())
            self.assertEqual(path.name, "advice.json")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["turn"], 3)
            self.assertEqual(data["advice"]["headline"], "出牌")
            self.assertIn("timestamp", data)

    def test_no_tmp_file_left(self):
        """原子写后无残留临时文件。"""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            publish_advice(d, Advice(kind="pass", headline="结束"), turn=1)
            self.assertEqual(list(d.glob(".advice_*.tmp")), [])


class PublishGameStateTest(unittest.TestCase):
    """盒子数据源 game_state.json：原子写 + D9 过滤（对手手牌只有数量）。"""

    @classmethod
    def setUpClass(cls):
        cls.result = parse_power_log(read_fixture_lines())  # 完整 fixture

    def _publish(self, friendly_player_id=1):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        d = Path(self._tmp.name)
        game = self.result.games[-1]
        snapshot = serialize_game(game, friendly_player_id, db=None)
        path = publish_game_state(d, snapshot, friendly_player_id)
        self.addCleanup(self._tmp.cleanup)
        data = json.loads(path.read_text(encoding="utf-8"))
        return d, path, data

    def test_atomic_write_and_fields(self):
        d, path, data = self._publish()
        self.assertEqual(path.name, GAME_STATE_FILENAME)
        self.assertIn("turn", data)
        self.assertIn("current_player_id", data)
        self.assertIn("friendly_player_id", data)
        self.assertIn("timestamp", data)
        self.assertEqual(len(data["players"]), 2)
        # 无残留临时文件
        self.assertEqual(list(d.glob(".state_*.tmp")), [])

    def test_opponent_hand_is_count_only(self):
        """D9：game_state.json 里对手手牌只有数量，绝无 card_id。"""
        _, _, data = self._publish(friendly_player_id=1)
        for pid, pv in data["players"].items():
            if int(pid) == data["friendly_player_id"]:
                self.assertIsInstance(pv["hand"], list)  # 我方手牌是明细
            else:
                # 对手手牌只有 {"count": N}
                self.assertIsInstance(pv["hand"], dict)
                self.assertEqual(set(pv["hand"]), {"count"})

    def test_snapshot_matches_serialize(self):
        """发布内容基于 serialize_game 输出，友方额外注入抽牌概率参考。

        publish 层对友方玩家加 draw_odds 字段（补 HDT 核心价值，前端盒子
        可显示）；对手与基础字段与 serialize_game 输出一致。
        """
        game = self.result.games[-1]
        snapshot = serialize_game(game, 1, db=None)
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = publish_game_state(Path(td), snapshot, 1)
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["turn"], snapshot.turn)
        self.assertEqual(data["current_player_id"], snapshot.current_player_id)
        self.assertEqual(data["friendly_player_id"], 1)
        for pid in snapshot.players:
            base = snapshot.players[pid].to_dict()
            if pid == 1 and base.get("deck_count", 0) > 0:
                # 友方（牌库非空）多了 draw_odds；其余字段应与 base 一致
                published = data["players"][str(pid)]
                self.assertIn("draw_odds", published)
                published_no_odds = {k: v for k, v in published.items() if k != "draw_odds"}
                self.assertEqual(published_no_odds, base)
            else:
                self.assertEqual(data["players"][str(pid)], base)


class TriggerFallbackTest(unittest.TestCase):
    """LLM 全部失败时降级为上一回合建议（spec L70：超时降级）。"""

    def test_failure_falls_back_to_last_advice(self):
        import tempfile

        class FlakyClient:
            def __init__(self):
                self.calls = 0

            def chat(self, system, user, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    return '{"kind":"play","headline":"第一回合建议","why":"","steps":[],"warning":""}'
                raise httpx.TimeoutException("超时")

        lines = read_fixture_lines()
        g1 = parse_power_log(lines[:3600]).games[0]  # turn 2（玩家1 当前）
        g2 = parse_power_log(lines[:4000]).games[0]  # turn 4（玩家1 当前）
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            trigger = TurnTrigger(friendly_player_id=1)
            client = FlakyClient()  # 同一个客户端：第 1 次成功、之后超时
            first = trigger.check_and_trigger(g1, None, client, d)
            self.assertEqual(first.headline, "第一回合建议")
            # 第二次触发：LLM 超时 → 降级为上一回合建议，且仍发布（turn=4）
            second = trigger.check_and_trigger(g2, None, client, d)
            self.assertTrue(second.degraded)
            self.assertEqual(second.headline, "第一回合建议")
            data = json.loads((d / "advice.json").read_text(encoding="utf-8"))
            self.assertEqual(data["turn"], 4)


# 合成的日志行（模拟真实格式）
_CREATE_GAME = "D 00:00:01 GameState.DebugPrintPower() - CREATE_GAME"
_PLAYER_ONE_DECL = (
    "D 00:00:01 GameState.DebugPrintPower() -     Player EntityID=2 PlayerID=1 GameAccountId=[hi=1 lo=2]"
)
_PLAYER_TWO_DECL = (
    "D 00:00:01 GameState.DebugPrintPower() -     Player EntityID=3 PlayerID=2 GameAccountId=[hi=1 lo=3]"
)
_TAG = "D 00:00:01 GameState.DebugPrintPower() -     TAG_CHANGE Entity={entity} tag={tag} value={value}"


def _current(entity: str, value: int) -> str:
    return _TAG.format(entity=entity, tag="CURRENT_PLAYER", value=value)


def _turn(value: int) -> str:
    return _TAG.format(entity="GameEntity", tag="TURN", value=value)


class IncrementalTurnDetectorTest(unittest.TestCase):
    """增量回合检测器（优化 2+3）——用真实 fixture 全量验证。"""

    @staticmethod
    def _feed_all(det: IncrementalTurnDetector, lines: list[str]) -> list[int]:
        """分批喂入（模拟 tail 增量），返回所有触发的回合号列表。"""
        triggered_turns = []
        for i in range(0, len(lines), 50):
            triggered_turns.extend(det.feed(lines[i : i + 50]))
        return triggered_turns

    def test_fixture_friendly1_triggers_even_turns(self):
        """friendly=1：fixture 全量应只在双数回合触发（2,4,...,14）。"""
        det = IncrementalTurnDetector(friendly_player_id=1)
        turns = self._feed_all(det, read_fixture_lines())
        self.assertEqual(turns, [2, 4, 6, 8, 10, 12, 14])

    def test_fixture_friendly2_triggers_odd_turns(self):
        """friendly=2：fixture 全量应只在单数回合触发（1,3,...,15）。

        修复回归：旧实现把 CURRENT_PLAYER 的 value 当玩家 id，friendly=2
        永不触发。真实日志单数回合是 PlayerTwo（玩家2）当前。
        """
        det = IncrementalTurnDetector(friendly_player_id=2)
        turns = self._feed_all(det, read_fixture_lines())
        self.assertEqual(turns, [1, 3, 5, 7, 9, 11, 13, 15])

    def test_trigger_window_ends_at_trigger_line(self):
        """触发窗口应截至触发回合的 TURN 行——同批内下一回合的行不污染。

        回归：旧实现全量解析所有累积行，同一批里若已含下一回合的行，
        快照被推到对方回合，本回合建议被吞（真实踩坑）。
        """
        det = IncrementalTurnDetector(friendly_player_id=1)
        lines = read_fixture_lines()
        # 用大批次（5600-5800）同时覆盖 turn 12 与 turn 13 的边界行
        turns = det.feed(lines[5600:5800])
        self.assertEqual(turns, [12])
        window = det.get_trigger_window(12)
        # 窗口最后一行应是 turn 12 的 TURN 行（turn 13 的行不在窗口内）
        self.assertIn("tag=TURN value=12", window[-1])
        self.assertNotIn("tag=TURN value=13", "\n".join(window))

    def test_name_form_maps_to_player_id(self):
        """名字形态 Entity=PlayerOne → 玩家1。"""
        det = IncrementalTurnDetector(friendly_player_id=1)
        det.feed([_CREATE_GAME, _PLAYER_ONE_DECL, _PLAYER_TWO_DECL,
                  _current("PlayerOne", 1)])
        self.assertEqual(det._current_player, 1)
        self.assertEqual(det.feed([_turn(2)]), [2])

    def test_numeric_form_maps_to_player_id(self):
        """数字形态 Entity=3 → 玩家2（CREATE_GAME 映射）。"""
        det = IncrementalTurnDetector(friendly_player_id=2)
        det.feed([_CREATE_GAME, _PLAYER_ONE_DECL, _PLAYER_TWO_DECL,
                  _current("3", 1)])
        self.assertEqual(det._current_player, 2)
        self.assertEqual(det.feed([_turn(1)]), [1])

    def test_value_zero_line_ignored(self):
        """CURRENT_PLAYER value=0（回合结束方）不应影响当前玩家判断。"""
        det = IncrementalTurnDetector(friendly_player_id=2)
        det.feed([_CREATE_GAME, _PLAYER_ONE_DECL, _PLAYER_TWO_DECL,
                  _current("PlayerOne", 0)])
        self.assertIsNone(det._current_player)
        # 没有 value=1 置位 → 回合变化不触发
        self.assertEqual(det.feed([_turn(1)]), [])

    def test_no_trigger_when_opponent_turn(self):
        """对手回合（current_player != friendly）不触发。"""
        det = IncrementalTurnDetector(friendly_player_id=1)
        det.feed([_CREATE_GAME, _PLAYER_ONE_DECL, _PLAYER_TWO_DECL,
                  _current("PlayerTwo", 1)])
        self.assertEqual(det.feed([_turn(3)]), [])

    def test_no_trigger_on_same_turn(self):
        """同一回合号不重复触发。"""
        det = IncrementalTurnDetector(friendly_player_id=1)
        det.feed([_CREATE_GAME, _PLAYER_ONE_DECL, _PLAYER_TWO_DECL,
                  _current("PlayerOne", 1)])
        self.assertEqual(det.feed([_turn(5)]), [5])
        self.assertEqual(det.feed([_turn(5)]), [])

    def test_accumulates_all_lines(self):
        """get_all_lines 返回累积的全部行。"""
        det = IncrementalTurnDetector(friendly_player_id=1)
        det.feed(["line1\n", "line2\n"])
        det.feed(["line3\n"])
        self.assertEqual(det.get_all_lines(), ["line1\n", "line2\n", "line3\n"])

    def test_reset_clears_state(self):
        """reset 后状态清零（新对局），实体映射与触发窗口一并清除。"""
        det = IncrementalTurnDetector(friendly_player_id=1)
        det.feed([_CREATE_GAME, _PLAYER_ONE_DECL, _PLAYER_TWO_DECL,
                  _current("PlayerOne", 1), _turn(5)])
        det.reset()
        self.assertEqual(det._last_turn, 0)
        self.assertIsNone(det._current_player)
        self.assertEqual(det._entity_to_player, {})
        self.assertEqual(det._trigger_upto, {})
        self.assertEqual(det.get_all_lines(), [])

    def test_new_game_clears_entity_mapping(self):
        """CREATE_GAME 行清空实体映射（跨对局不串味）。"""
        det = IncrementalTurnDetector(friendly_player_id=2)
        det.feed([_CREATE_GAME, _PLAYER_ONE_DECL, _PLAYER_TWO_DECL])
        self.assertEqual(det._entity_to_player, {2: 1, 3: 2})
        det.feed([_CREATE_GAME])  # 新对局
        self.assertEqual(det._entity_to_player, {})


class DetectorEndToEndTest(unittest.TestCase):
    """检测器 → 触发窗口全量解析 → check_and_trigger 端到端（模拟 worker）。"""

    def test_full_fixture_produces_advices(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            client = MockClient()
            detector = IncrementalTurnDetector(friendly_player_id=1)
            trigger = TurnTrigger(friendly_player_id=1)
            advices = 0
            all_lines = read_fixture_lines()
            for i in range(0, len(all_lines), 200):
                for turn in detector.feed(all_lines[i : i + 200]):
                    result = parse_power_log(detector.get_trigger_window(turn))
                    game = result.games[-1]
                    if trigger.check_and_trigger(game, None, client, d) is not None:
                        advices += 1
            # friendly=1 有 7 个友方回合，应发布 7 条建议
            self.assertEqual(advices, 7)
            self.assertTrue((d / "advice.json").exists())


if __name__ == "__main__":
    unittest.main()
