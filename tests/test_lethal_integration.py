"""T-L2 斩杀提示注入 LLM prompt 的集成测试。

验证 compute_lethal 的结果被 build_user_prompt 注入：教练的 prompt 里
出现精确的"本回合可斩杀/场攻 N/距斩杀差 M"信息——让 LLM 不必算术，
聚焦定性决策。这是补 LLM 算术短板的最后一公里。
"""

import logging
import unittest

logging.disable(logging.WARNING)

from hscoach.coach import build_user_prompt, SYSTEM_PROMPT
from hscoach.lethal import LethalCheck, compute_lethal
from hscoach.state import CardView, GameSnapshot, PlayerView

logger = logging.getLogger(__name__)


def _card(name="", attack=None, health=None, cost=0, flags=None, text="", card_id=None):
    return CardView(
        card_id=card_id, name=name, cost=cost, attack=attack, health=health,
        flags=flags or [], text=text,
    )


def _player(health=30, armor=0, mana=10, max_mana=10, hand=None, board=None):
    return PlayerView(
        name="测试", hero=None, health=health, armor=armor, mana=mana,
        max_mana=max_mana, hand=hand or [], hand_is_hidden=False,
        board=board or [], deck_count=0,
    )


def _opp(health=30, armor=0):
    return PlayerView(
        name="对手", hero=None, health=health, armor=armor, mana=10,
        max_mana=10, hand=4, hand_is_hidden=True, board=[], deck_count=0,
    )


def _snap(friendly, opponent):
    return GameSnapshot(turn=6, current_player_id=1, players={1: friendly, 2: opponent})


class PromptInjectionTest(unittest.TestCase):
    """build_user_prompt 注入 lethal.summary() 到 prompt。"""

    def test_lethal_scenario_injected_into_prompt(self):
        """斩杀局面：prompt 含'可斩杀'与伤害明细。"""
        friendly = _player(
            board=[_card(name="雪人", attack=7, health=7)],
            hand=[_card(name="火球术", cost=4, text="造成 6 点伤害。")],
            mana=10,
        )
        opp = _opp(health=10)
        snap = _snap(friendly, opp)
        check = compute_lethal(snap, friendly_player_id=1)
        self.assertTrue(check.lethal)

        prompt = build_user_prompt(snap, friendly_player_id=1, lethal=check)
        self.assertIn("斩杀", prompt)
        self.assertIn("13", prompt)  # 7+6

    def test_non_lethal_injects_deficit(self):
        """非斩杀：prompt 含场攻与差额。"""
        friendly = _player(board=[_card(name="雪人", attack=3, health=3)])
        opp = _opp(health=10)
        snap = _snap(friendly, opp)
        check = compute_lethal(snap, friendly_player_id=1)
        self.assertFalse(check.lethal)

        prompt = build_user_prompt(snap, friendly_player_id=1, lethal=check)
        # 含差额信息
        self.assertIn("3", prompt)

    def test_zero_damage_injected(self):
        """空场无伤害：prompt 注入'无确定直接伤害'。"""
        friendly = _player()
        opp = _opp(health=30)
        snap = _snap(friendly, opp)
        check = compute_lethal(snap, friendly_player_id=1)
        prompt = build_user_prompt(snap, friendly_player_id=1, lethal=check)
        self.assertIn("0", prompt)

    def test_system_prompt_mentions_lethal_guidance(self):
        """SYSTEM_PROMPT 应引导 LLM 重视代码给出的斩杀判定。"""
        # LLM 不应自行算术；应参考注入的精确判定
        self.assertIn("斩杀", SYSTEM_PROMPT)


class ManualLethalInjectionTest(unittest.TestCase):
    """调用方可手动传 LethalCheck（不依赖 compute_lethal）。

    场景：教练可能想用更复杂的 lethal 判定（如考虑武器），手动构造后
    注入。build_user_prompt 接受 LethalCheck 对象即可。
    """

    def test_manual_check_injected(self):
        friendly = _player(board=[_card(attack=5, health=5)])
        opp = _opp(health=5)
        snap = _snap(friendly, opp)
        manual = LethalCheck(available_damage=5, lethal=True,
                             detail=[{"name": "随从", "damage": 5, "source": "board"}],
                             deficit=0)
        prompt = build_user_prompt(snap, friendly_player_id=1, lethal=manual)
        self.assertIn("斩杀", prompt)
        self.assertIn("5", prompt)


if __name__ == "__main__":
    unittest.main()
