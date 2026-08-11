"""T-D2 抽牌概率接入测试（修复 Spec 审查 #1：零接入）。

probability.py 与测试齐全，但从未被 build_user_prompt / game_state.json /
前端消费——"造了枪没上火线"。本测试验证接入的最后一公里：
- draw_odds_table 给牌库剩余 N 张时的 1-of/2-of 概率参考
- build_user_prompt 注入抽牌概率行
- publish_game_state 发布 draw_odds 字段供前端盒子显示
"""

import json
import logging
import unittest
from pathlib import Path

logging.disable(logging.WARNING)

from hscoach.coach import build_user_prompt
from hscoach.lethal import compute_lethal  # noqa: F401  确保模块可导入
from hscoach.probability import draw_at_least_one, draw_odds_table
from hscoach.state import CardView, GameSnapshot, PlayerView
from hscoach.trigger import GAME_STATE_FILENAME, publish_game_state

logger = logging.getLogger(__name__)


def _player(health=30, armor=0, mana=10, max_mana=10, hand=None, board=None, deck_count=0):
    return PlayerView(
        name="测试", hero=None, health=health, armor=armor, mana=mana,
        max_mana=max_mana, hand=hand or [], hand_is_hidden=False,
        board=board or [], deck_count=deck_count,
    )


def _opp(health=30, armor=0, deck_count=25):
    return PlayerView(
        name="对手", hero=None, health=health, armor=armor, mana=10,
        max_mana=10, hand=4, hand_is_hidden=True, board=[], deck_count=deck_count,
    )


def _snap(friendly, opponent):
    return GameSnapshot(turn=6, current_player_id=1, players={1: friendly, 2: opponent})


class DrawOddsTableTest(unittest.TestCase):
    """draw_odds_table：牌库剩余 N 张时的抽牌概率参考。"""

    def test_returns_dict_with_one_and_two_copy(self):
        table = draw_odds_table(deck_size=25)
        self.assertIn("one_copy_next_draw", table)
        self.assertIn("two_copy_next_draw", table)

    def test_values_are_probabilities_in_unit_interval(self):
        table = draw_odds_table(deck_size=20)
        for key in ("one_copy_next_draw", "two_copy_next_draw"):
            p = table[key]
            self.assertGreater(p, 0.0)
            self.assertLess(p, 1.0)

    def test_two_copy_higher_than_one_copy(self):
        """2-of 抽中概率应高于 1-of。"""
        table = draw_odds_table(deck_size=25)
        self.assertGreater(table["two_copy_next_draw"], table["one_copy_next_draw"])

    def test_matches_hypergeometric(self):
        """参考值与 draw_at_least_one 一致。"""
        table = draw_odds_table(deck_size=25)
        self.assertAlmostEqual(table["two_copy_next_draw"], draw_at_least_one(25, 2, 1))

    def test_small_deck_higher_probability(self):
        """牌库越小，抽中概率越高（单调）。"""
        big = draw_odds_table(deck_size=30)
        small = draw_odds_table(deck_size=10)
        self.assertGreater(small["two_copy_next_draw"], big["two_copy_next_draw"])

    def test_zero_deck_returns_zero(self):
        """空牌库：抽中概率 0。"""
        table = draw_odds_table(deck_size=0)
        self.assertEqual(table["one_copy_next_draw"], 0.0)
        self.assertEqual(table["two_copy_next_draw"], 0.0)


class PromptInjectionTest(unittest.TestCase):
    """build_user_prompt 注入抽牌概率行（让 LLM 感知随机性）。"""

    def test_prompt_contains_draw_odds(self):
        """prompt 含抽牌概率参考行。"""
        friendly = _player(deck_count=25)
        opp = _opp()
        snap = _snap(friendly, opp)
        prompt = build_user_prompt(snap, friendly_player_id=1)
        self.assertIn("抽牌", prompt)

    def test_prompt_draw_odds_reflects_deck_size(self):
        """不同牌库大小应产生不同概率文本。"""
        p_big = build_user_prompt(_snap(_player(deck_count=30), _opp()), 1)
        p_small = build_user_prompt(_snap(_player(deck_count=10), _opp()), 1)
        self.assertNotEqual(p_big, p_small)


class GameStatePublishTest(unittest.TestCase):
    """publish_game_state 发布 draw_odds 字段（前端盒子可显示）。"""

    def test_game_state_json_contains_draw_odds(self):
        """game_state.json 含友方 draw_odds 字段。"""
        friendly = _player(deck_count=25)
        opp = _opp(deck_count=20)
        snap = _snap(friendly, opp)
        tmp = Path(__file__).resolve().parent / "_tmp_draw_odds_test"
        tmp.mkdir(exist_ok=True)
        try:
            publish_game_state(tmp, snap, friendly_player_id=1)
            data = json.loads((tmp / GAME_STATE_FILENAME).read_text(encoding="utf-8"))
            friendly_state = data["players"]["1"]
            self.assertIn("draw_odds", friendly_state)
            odds = friendly_state["draw_odds"]
            self.assertIn("one_copy_next_draw", odds)
            self.assertIn("two_copy_next_draw", odds)
        finally:
            (tmp / GAME_STATE_FILENAME).unlink(missing_ok=True)
            tmp.rmdir()


if __name__ == "__main__":
    unittest.main()
