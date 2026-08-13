"""T-S2 记牌器数据接入教练 prompt（坟场/奥秘池/疲劳，全公开信息）。

竞品差距：HDT/盒子把"对方已出牌、猜奥秘"显示给玩家；本品进一步把
这些注入 LLM prompt，让教练基于"对手还剩什么威胁"做决策，而不是
只看当前场面。
"""

import logging
import unittest

logging.disable(logging.WARNING)

from hscoach.coach import build_user_prompt
from tests._helpers import (
    make_card as _card,
    make_opp as _opp,
    make_player as _player,
    make_snapshot as _snap,
)


class TrackerInfoInPromptTest(unittest.TestCase):
    """坟场/奥秘/疲劳信息注入 build_user_prompt。"""

    def test_played_cards_injected(self):
        friendly = _player(played_cards=[_card(name="火球术"), _card(name="寒冰箭")])
        opp = _opp(played_cards=[_card(name="奥金斧"), _card(name="苦痛侍僧")])
        prompt = build_user_prompt(_snap(friendly, opp), friendly_player_id=1)
        self.assertIn("火球术", prompt)
        self.assertIn("奥金斧", prompt)
        self.assertIn("苦痛侍僧", prompt)

    def test_opponent_secrets_with_pool(self):
        opp = _opp(secrets=2, possible_secrets=["法术反制", "寒冰护体", "爆炸符文"])
        prompt = build_user_prompt(_snap(_player(), opp), friendly_player_id=1)
        self.assertIn("奥秘", prompt)
        self.assertIn("法术反制", prompt)
        self.assertIn("爆炸符文", prompt)

    def test_opponent_secrets_without_pool(self):
        """无标准池数据（生成奥秘）时如实说明，不臆造。"""
        opp = _opp(secrets=1, possible_secrets=[])
        prompt = build_user_prompt(_snap(_player(), opp), friendly_player_id=1)
        self.assertIn("奥秘", prompt)

    def test_no_secrets_no_section(self):
        prompt = build_user_prompt(_snap(_player(), _opp()), friendly_player_id=1)
        self.assertNotIn("奥秘", prompt)

    def test_opponent_fatigue_hint(self):
        opp = _opp(deck_count=0, fatigue=2)
        prompt = build_user_prompt(_snap(_player(), opp), friendly_player_id=1)
        self.assertIn("疲劳", prompt)
        self.assertIn("3", prompt)  # 已疲劳 2 次 → 下回合 3 点

    def test_friendly_fatigue_hint(self):
        friendly = _player(deck_count=0, fatigue=1)
        prompt = build_user_prompt(_snap(friendly, _opp()), friendly_player_id=1)
        self.assertIn("疲劳", prompt)
        self.assertIn("2", prompt)

    def test_no_fatigue_when_decks_remain(self):
        prompt = build_user_prompt(
            _snap(_player(deck_count=20), _opp(deck_count=20)), friendly_player_id=1
        )
        self.assertNotIn("疲劳", prompt)


if __name__ == "__main__":
    unittest.main()
