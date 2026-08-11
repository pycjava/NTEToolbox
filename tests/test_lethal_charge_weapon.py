"""T-L3 冲锋/突袭随从与武器计入斩杀（修复 Spec 审查 #2/#3）。

原实现只认"造成 N 点伤害"法术，忽略：
- 手牌中带冲锋/突袭的随从（本回合可打出并攻击 → 确定伤害）
- 已装备的武器（英雄本回合可挥砍 → 确定伤害）

这两类都是"确定的直接伤害"，保守原则要求计入（宁可多报让 LLM 评估，
也好过漏报斩杀）。注意：冲锋随从需打出（受法力约束），突袭随从打出后
本回合不能打脸（只能打随从）——因此只有【冲锋】计入英雄伤害，突袭不计。
"""

import unittest

from hscoach.lethal import compute_lethal
from hscoach.state import CardView, GameSnapshot, PlayerView


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


class ChargeMinionInHandTest(unittest.TestCase):
    """手牌中冲锋随从：本回合可打出并直接打脸（受法力约束）。"""

    def test_charge_minion_damage_counts(self):
        """冲锋随从 attack 计入斩杀（需可支付费用）。"""
        charger = _card(name="冲锋怪", attack=5, health=5, cost=4, flags=["冲锋"])
        friendly = _player(mana=4, hand=[charger])
        opp = _opp(health=5)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 5)
        self.assertTrue(check.lethal)

    def test_charge_minion_over_mana_excluded(self):
        """超费冲锋随从打不出，不计入。"""
        charger = _card(name="冲锋怪", attack=5, health=5, cost=8, flags=["冲锋"])
        friendly = _player(mana=4, hand=[charger])
        opp = _opp(health=5)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)

    def test_charge_minion_detail_lists_source(self):
        """冲锋随从在 detail 里标注来源。"""
        charger = _card(name="狼骑兵", attack=3, health=3, cost=3, flags=["冲锋"])
        friendly = _player(mana=3, hand=[charger])
        check = compute_lethal(_snap(friendly, _opp()))
        names = [d["name"] for d in check.detail]
        self.assertIn("狼骑兵", names)


class RushMinionNotCountedTest(unittest.TestCase):
    """突袭随从本回合不能打脸（只能打随从）→ 不计入英雄伤害。

    保守：突袭是确定能攻击随从，但不是英雄伤害。斩杀判定针对英雄，
    故突袭不计入。避免误报斩杀。
    """

    def test_rush_minion_not_in_face_damage(self):
        rusher = _card(name="突袭怪", attack=5, health=5, cost=4, flags=["突袭"])
        friendly = _player(mana=4, hand=[rusher])
        opp = _opp(health=5)
        check = compute_lethal(_snap(friendly, opp))
        # 突袭不能打脸，不计入英雄斩杀伤害
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)


class EquippedWeaponTest(unittest.TestCase):
    """已装备武器：英雄本回合可挥砍（若未疲劳/未已尽）。

    武器在场面（PLAY zone），attack 计入。武器有"已尽"时不计（用过了）。
    实现：武器作为 board 实体，其 attack 应被场攻统计纳入。
    """

    def test_weapon_attack_counts_as_board(self):
        """武器 attack 计入场攻（英雄可挥砍打脸）。"""
        weapon = _card(name="奥金斧", attack=5, health=None, cost=5)
        friendly = _player(mana=10, board=[weapon])
        opp = _opp(health=5)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 5)
        self.assertTrue(check.lethal)

    def test_weapon_plus_minion_sum(self):
        """武器 + 随从攻击力叠加。"""
        weapon = _card(name="武器", attack=3, health=None)
        minion = _card(name="随从", attack=4, health=4)
        friendly = _player(board=[weapon, minion])
        opp = _opp(health=7)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 7)


if __name__ == "__main__":
    unittest.main()
