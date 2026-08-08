"""T8(08) 置顶窗 UI 测试。

UI 组件本身难以单元测试（需真实启动 tkinter 主循环），
这里测可分离的核心逻辑（overlay.parse_display_fields / parse_tracker_fields，
与 UI 共用单一来源）：
- advice.json 解析成显示字段
- 内容格式化（步骤、警示）
- kind 图标映射（KIND_ICONS 单一词典，UI 与测试共用）
- game_state.json 解析成盒子（记牌器）显示字段：回合/当前玩家/双方
  血量/法力/手牌数/牌库剩余

控制窗（永不穿透的退出按钮）的窗口行为见手动验证记录：
启动 overlay → 默认穿透只作用于建议窗，控制窗始终可点。
"""

import json
import tempfile
import unittest
from pathlib import Path

from hscoach.coach import Advice
from hscoach.overlay import KIND_ICONS, parse_display_fields, parse_tracker_fields
from hscoach.trigger import publish_advice


class OverlayContentParseTest(unittest.TestCase):
    """测试 UI 从 advice.json 提取显示字段的逻辑（不启动 tkinter）。"""

    def test_parses_full_advice(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            adv = Advice(
                kind="play",
                headline="出火球术打脸",
                why="能斩杀对手",
                steps=["用火球术", "瞄准敌方英雄"],
                warning="注意对手有反制",
            )
            publish_advice(d, adv, turn=7)
            data = json.loads((d / "advice.json").read_text(encoding="utf-8"))
            fields = parse_display_fields(data)
            self.assertIn("T7", fields["headline"])
            self.assertIn("出火球术打脸", fields["headline"])
            self.assertIn("⚔️", fields["headline"])
            self.assertEqual(fields["why"], "能斩杀对手")
            self.assertIn("用火球术", fields["steps"])
            self.assertIn("⚠ 注意对手有反制", fields["steps"])

    def test_handles_minimal_advice(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            publish_advice(d, Advice(kind="pass", headline="结束回合"), turn=1)
            data = json.loads((d / "advice.json").read_text(encoding="utf-8"))
            fields = parse_display_fields(data)
            self.assertIn("T1", fields["headline"])
            self.assertIn("⏭", fields["headline"])
            self.assertEqual(fields["steps"], "")

    def test_uncertain_kind_uses_question_icon(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            publish_advice(d, Advice(kind="uncertain", headline="两种都行"), turn=3)
            data = json.loads((d / "advice.json").read_text(encoding="utf-8"))
            fields = parse_display_fields(data)
            self.assertIn("❓", fields["headline"])

    def test_steps_without_warning(self):
        data = {
            "turn": 2,
            "advice": {
                "kind": "trade",
                "headline": "交换",
                "why": "解场",
                "steps": ["随从A撞随从B"],
                "warning": "",
            },
        }
        fields = parse_display_fields(data)
        self.assertIn("随从A撞随从B", fields["steps"])
        self.assertNotIn("⚠", fields["steps"])

    def test_icon_map_covers_all_kinds(self):
        """KIND_ICONS 覆盖全部 kind 取值（与 coach.KINDS 对齐）。"""
        self.assertEqual(
            set(KIND_ICONS),
            {"play", "trade", "pass", "uncertain"},
        )
        # 未知 kind 不崩，图标为空
        fields = parse_display_fields({"turn": 1, "advice": {"kind": "hack", "headline": "x"}})
        self.assertEqual(fields["headline"], "T1  x")


class TrackerBoxParseTest(unittest.TestCase):
    """盒子（记牌器）面板：从 game_state.json 提取显示字段。"""

    def _state(self, players=None, turn=5, current=1, friendly=1):
        return {
            "turn": turn,
            "current_player_id": current,
            "friendly_player_id": friendly,
            "players": players
            or {
                "1": {
                    "health": 30, "armor": 2, "mana": 4, "max_mana": 5,
                    "hand": [{"name": "火球术"}], "board": [], "deck_count": 22,
                },
                "2": {
                    "health": 24, "armor": 0, "mana": 3, "max_mana": 5,
                    "hand": {"count": 6}, "board": [], "deck_count": 20,
                },
            },
        }

    def test_title_shows_turn_and_current_player(self):
        fields = parse_tracker_fields(self._state(current=1, friendly=1))
        self.assertIn("T5", fields["title"])
        self.assertIn("我方回合", fields["title"])

    def test_opponent_turn_title(self):
        fields = parse_tracker_fields(self._state(current=2, friendly=1))
        self.assertIn("对手回合", fields["title"])

    def test_lines_mark_friendly_and_opponent(self):
        fields = parse_tracker_fields(self._state(friendly=1))
        self.assertEqual(len(fields["lines"]), 2)
        friendly_line = fields["lines"][0]
        opp_line = fields["lines"][1]
        self.assertIn("我方", friendly_line)
        self.assertIn("对手", opp_line)
        self.assertIn("❤30", friendly_line)
        self.assertIn("🛡2", friendly_line)
        self.assertIn("⚡4/5", friendly_line)
        self.assertIn("📚22", friendly_line)
        self.assertIn("❤24", opp_line)
        self.assertIn("📚20", opp_line)

    def test_opponent_hand_count_shown_not_cards(self):
        """D9：对手手牌只显示数量（game_state.json 已过滤，UI 不再展开）。"""
        fields = parse_tracker_fields(self._state(friendly=1))
        opp_line = fields["lines"][1]
        self.assertIn("✋6", opp_line)
        self.assertNotIn("火球术", opp_line)

    def test_friendly_hand_is_count_too(self):
        """盒子里我方手牌也只显示数量（记牌器风格，细节自己看游戏）。"""
        fields = parse_tracker_fields(self._state(friendly=1))
        self.assertIn("✋1", fields["lines"][0])
        self.assertNotIn("火球术", fields["lines"][0])

    def test_empty_state_has_no_lines(self):
        fields = parse_tracker_fields({"turn": 0, "players": {}})
        self.assertEqual(fields["lines"], [])
        self.assertIn("T0", fields["title"])

    def test_unknown_current_player_no_crash(self):
        fields = parse_tracker_fields(self._state(current=None, friendly=1))
        self.assertEqual(fields["title"], "T5")

    def test_real_fixture_state_publishes_d9_safe(self):
        """端到端：真实 fixture → 序列化 → 发布 → 盒子解析，对手手牌只见数量。"""
        from hscoach.log_parser import parse_power_log
        from hscoach.state import serialize_game
        from hscoach.trigger import publish_game_state
        from tests._helpers import read_fixture_lines

        result = parse_power_log(read_fixture_lines())
        game = result.games[-1]
        with tempfile.TemporaryDirectory() as td:
            snapshot = serialize_game(game, friendly_player_id=1, db=None)
            path = publish_game_state(Path(td), snapshot, 1)
            data = json.loads(path.read_text(encoding="utf-8"))
            fields = parse_tracker_fields(data)
        self.assertEqual(len(fields["lines"]), 2)
        joined = "\n".join(fields["lines"])
        self.assertIn("我方", joined)
        self.assertIn("对手", joined)
        # 对手手牌数量 ≥ 0（fixture 中对手手牌区只有数量字段）
        opp_line = [l for l in fields["lines"] if l.startswith("对手")][0]
        self.assertRegex(opp_line, r"✋\d+")


if __name__ == "__main__":
    unittest.main()
