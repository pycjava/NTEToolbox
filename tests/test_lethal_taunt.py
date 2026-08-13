"""T-L4 斩杀计算器的嘲讽阻挡模型（竞品对齐：HDT 斩杀插件会算嘲讽）。

原实现把"场攻 + 手牌伤害"全部当作可打脸伤害，存在两类缺陷：
1. 对手有嘲讽随从时误报斩杀（打脸攻击必须先清光嘲讽，过量伤害
   会浪费在嘲讽身上）——违反"绝不误报"原则，比漏报致命得多。
2. 圣盾嘲讽需要额外一击（护盾吸收一次攻击），单发高攻无法击杀。

模型（纯确定性，保守原则不变）：
- 法术伤害永远可以打脸（嘲讽挡不住指定英雄的法术）。
- 随从/英雄/冲锋的攻击伤害受嘲讽阻挡：必须选一个"花费最小伤害"
  的子集清光嘲讽（子集和 DP 处理过量伤害浪费），剩余才打脸。
- 圣盾嘲讽：清除需 taunt 数 + 圣盾数 次攻击，总伤害 >= 嘲讽总血量
  + 圣盾数（每层护盾至少吸收 1 点）。
- 免疫嘲讽：无法被伤害清除，攻击永远打不到脸。
"""

import unittest

from hscoach.lethal import compute_lethal
from hscoach.state import CardView, GameSnapshot, PlayerView


def _card(name="", attack=None, health=None, cost=0, flags=None, text="", card_type=""):
    return CardView(
        card_id=None, name=name, cost=cost, attack=attack, health=health,
        flags=flags or [], text=text, card_type=card_type,
    )


def _player(health=30, armor=0, mana=10, max_mana=10, hand=None, board=None):
    return PlayerView(
        name="测试", hero=None, health=health, armor=armor, mana=mana,
        max_mana=max_mana, hand=hand or [], hand_is_hidden=False,
        board=board or [], deck_count=0,
    )


def _opp(health=30, armor=0, board=None):
    return PlayerView(
        name="对手", hero=None, health=health, armor=armor, mana=10,
        max_mana=10, hand=4, hand_is_hidden=True, board=board or [], deck_count=0,
    )


def _snap(friendly, opponent):
    return GameSnapshot(turn=6, current_player_id=1, players={1: friendly, 2: opponent})


class TauntBlockingTest(unittest.TestCase):
    """对手嘲讽随从：攻击伤害必须先清嘲讽，法术可绕过打脸。"""

    def test_taunt_blocks_all_attack_damage(self):
        """5 攻随从 vs 3 血嘲讽：打不到脸 → available=0（原实现误报 5）。"""
        friendly = _player(board=[_card(name="雪人", attack=5, health=5)])
        opp = _opp(health=5, board=[_card(name="嘲讽怪", attack=1, health=3, flags=["嘲讽"])])
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_spell_bypasses_taunt(self):
        """法术直接打脸不受嘲讽阻挡。"""
        fireball = _card(name="火球术", cost=4, text="对一个角色造成 6 点伤害。")
        friendly = _player(mana=10, hand=[fireball])
        opp = _opp(health=6, board=[_card(name="嘲讽怪", attack=1, health=3, flags=["嘲讽"])])
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 6)
        self.assertTrue(check.lethal)

    def test_attack_surplus_after_clearing_taunt(self):
        """两个 4 攻随从 vs 3 血嘲讽：一个清嘲讽（4 全花），一个打脸 → 4。"""
        friendly = _player(board=[
            _card(name="a", attack=4, health=4),
            _card(name="b", attack=4, health=4),
        ])
        opp = _opp(health=4, board=[_card(name="嘲讽怪", attack=1, health=3, flags=["嘲讽"])])
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 4)
        self.assertTrue(check.lethal)

    def test_overkill_waste_not_face_damage(self):
        """单只 8 攻随从 vs 5 血嘲讽：8 点全砸嘲讽（过量 3 浪费），打脸 0。

        原实现会误报 8 点打脸（错误斩杀）；子集和模型正确处理过量浪费。
        """
        friendly = _player(board=[_card(name="大怪", attack=8, health=8)])
        opp = _opp(health=3, board=[_card(name="嘲讽怪", attack=1, health=5, flags=["嘲讽"])])
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_two_taunts_need_all_cleared(self):
        """两个嘲讽（3+4 血）：单只 10 攻随从只能打一个嘲讽，另一个仍挡脸。

        每次攻击最多打一个嘲讽 → 打脸 0（子集需含 >= 嘲讽数 的条目）。
        """
        friendly = _player(board=[_card(name="大怪", attack=10, health=10)])
        opp = _opp(
            health=10,
            board=[
                _card(name="t1", attack=1, health=3, flags=["嘲讽"]),
                _card(name="t2", attack=1, health=4, flags=["嘲讽"]),
            ],
        )
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_two_attackers_clear_two_taunts(self):
        """两只随从（5+4）打两只嘲讽（3+4）：全花在嘲讽上，打脸 0。"""
        friendly = _player(board=[
            _card(name="a", attack=5, health=5),
            _card(name="b", attack=4, health=4),
        ])
        opp = _opp(
            health=5,
            board=[
                _card(name="t1", attack=1, health=3, flags=["嘲讽"]),
                _card(name="t2", attack=1, health=4, flags=["嘲讽"]),
            ],
        )
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_spell_plus_attack_clear_taunt_together(self):
        """法术可用来清嘲讽（如 4 伤法术清 3 血嘲讽），腾出攻击打脸。

        场攻 4（随从）+ 手牌 4 伤法术，嘲讽 3 血：法术清嘲讽（4 全花，
        过量 1），随从 4 点打脸 → available=4。
        """
        spell = _card(name="奥术射击", cost=1, text="造成 4 点伤害。")
        friendly = _player(mana=10, board=[_card(name="随从", attack=4, health=4)], hand=[spell])
        opp = _opp(health=4, board=[_card(name="嘲讽怪", attack=1, health=3, flags=["嘲讽"])])
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 4)
        self.assertTrue(check.lethal)

    def test_charge_minion_blocked_by_taunt(self):
        """冲锋随从是攻击伤害，同样受嘲讽阻挡。"""
        charger = _card(name="狼骑兵", attack=4, health=4, cost=3, flags=["冲锋"])
        friendly = _player(mana=3, hand=[charger])
        opp = _opp(health=4, board=[_card(name="嘲讽怪", attack=1, health=3, flags=["嘲讽"])])
        check = compute_lethal(_snap(friendly, opp))
        # 冲锋 4 点全部砸嘲讽（过量 1），打脸 0
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)


class WindfuryTest(unittest.TestCase):
    """风怒（WINDFURY）：本回合可攻击两次 → 攻击伤害加倍。

    竞品对齐：HDT 斩杀插件把风怒随从算两次攻击。
    """

    def test_windfury_minion_counts_twice(self):
        """风怒 3 攻随从 = 两次 3 点攻击 = 6 点。"""
        friendly = _player(board=[_card(name="风怒怪", attack=3, health=3, flags=["风怒"])])
        opp = _opp(health=6)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 6)
        self.assertTrue(check.lethal)

    def test_windfury_hero_counts_twice(self):
        """风怒英雄（如风怒武器）：两次挥砍。"""
        hero = _card(name="古尔丹", attack=4, health=30, flags=["风怒"], card_type="HERO")
        friendly = _player(board=[hero])
        opp = _opp(health=8)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 8)
        self.assertTrue(check.lethal)

    def test_windfury_first_hit_clears_taunt_second_hits_face(self):
        """风怒 4 攻 vs 3 血嘲讽：第一次清嘲讽，第二次打脸 → 4。"""
        friendly = _player(board=[_card(name="风怒怪", attack=4, health=4, flags=["风怒"])])
        opp = _opp(health=4, board=[_card(name="嘲讽怪", attack=1, health=3, flags=["嘲讽"])])
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 4)
        self.assertTrue(check.lethal)

    def test_windfury_charge_minion_counts_twice(self):
        """手牌风怒冲锋随从：打出后攻击两次（费用只付一次）。"""
        charger = _card(name="风怒冲锋", attack=3, health=3, cost=3, flags=["冲锋", "风怒"])
        friendly = _player(mana=3, hand=[charger])
        opp = _opp(health=6)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 6)
        self.assertTrue(check.lethal)

    def test_windfury_minion_two_hits_on_one_taunt(self):
        """风怒 3 攻 vs 5 血嘲讽：两次攻击（3+3）恰好清掉嘲讽，打脸 0。"""
        friendly = _player(board=[_card(name="风怒怪", attack=3, health=3, flags=["风怒"])])
        opp = _opp(health=5, board=[_card(name="嘲讽怪", attack=1, health=5, flags=["嘲讽"])])
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)


class SpellTargetFilterTest(unittest.TestCase):
    """保守识别"确定可打脸"的法术：宁可漏报，绝不误报。

    打脸：无目标对象（"造成 N 点伤害"）、"对一个角色"、"对所有敌人"。
    不能打脸：只对随从（"对一个随从"/"对所有(敌方)随从"）、随机目标、
    随机分配、触发式（战吼/亡语）。
    """

    def test_minion_only_spell_excluded(self):
        """'对一个随从造成 3 点伤害'不能打脸 → 不计。"""
        spell = _card(name="炎枪术", cost=5, text="对一个随从造成 25 点伤害。")
        friendly = _player(mana=10, hand=[spell])
        opp = _opp(health=25)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_all_enemy_minions_spell_excluded(self):
        """'对所有敌方随从造成 5 点伤害'（AOE 只打随从）→ 不计。"""
        spell = _card(name="烈焰风暴", cost=7, text="对所有敌方随从造成 5 点伤害。")
        friendly = _player(mana=10, hand=[spell])
        opp = _opp(health=5)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)

    def test_random_target_spell_excluded(self):
        """'随机对一个敌人造成 3 点伤害'目标不确定 → 不计。"""
        spell = _card(name="奥术飞弹", cost=1, text="随机对一个敌人造成 1 点伤害。")
        friendly = _player(mana=10, hand=[spell])
        opp = _opp(health=1)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)

    def test_random_split_spell_excluded(self):
        """'造成 5 点伤害，随机分配'伤害分配不确定 → 不计。"""
        spell = _card(name="邪魂审判", cost=2, text="造成 5 点伤害，随机分配到所有敌人。")
        friendly = _player(mana=10, hand=[spell])
        opp = _opp(health=5)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)

    def test_aoe_all_enemies_counts(self):
        """'对所有敌人造成 3 点伤害'（含英雄）→ 可打脸，计入。"""
        spell = _card(name="亵渎", cost=2, text="对所有敌人造成 3 点伤害。")
        friendly = _player(mana=10, hand=[spell])
        opp = _opp(health=3)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 3)
        self.assertTrue(check.lethal)

    def test_character_target_spell_counts(self):
        """'对一个角色造成 3 点伤害'（角色含英雄）→ 可打脸。"""
        spell = _card(name="寒冰箭", cost=2, text="对一个角色造成 3 点伤害，并使其冻结。")
        friendly = _player(mana=10, hand=[spell])
        opp = _opp(health=3)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 3)
        self.assertTrue(check.lethal)

    def test_battlecry_minion_not_counted_as_spell(self):
        """随从的战吼/亡语伤害文本不算"本回合确定打脸"（原实现误报）。

        例如 3/2 随从带"战吼：对一个随从造成 3 点伤害"——战吼只能打
        随从、时机也未必可控，绝不能算作打脸伤害。
        """
        minion = _card(
            name="战吼怪", attack=3, health=2, cost=3,
            text="战吼：对一个随从造成 3 点伤害。", card_type="MINION",
        )
        friendly = _player(mana=10, hand=[minion])
        opp = _opp(health=3)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)


class DivineShieldAndImmuneTauntTest(unittest.TestCase):
    """圣盾嘲讽：护盾吸收一次攻击 → 清除需额外一击。

    免疫嘲讽：无法被伤害清除 → 攻击永远打不到脸。
    """

    def test_divine_shield_taunt_needs_extra_hit(self):
        """圣盾 3 血嘲讽 + 对手 4 血，己方 5+4 攻。

        真实：4 攻打盾（护盾吸收，嘲讽存活），5 攻打嘲讽（过量 2），
        打脸 0。原模型误以为 4 攻能清掉嘲讽 → 误报 5 点打脸斩杀。
        """
        friendly = _player(board=[
            _card(name="a", attack=5, health=5),
            _card(name="b", attack=4, health=4),
        ])
        opp = _opp(
            health=4,
            board=[_card(name="圣盾嘲讽", attack=1, health=3, flags=["嘲讽", "圣盾"])],
        )
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_divine_shield_taunt_cleared_with_two_hits(self):
        """两只 4 攻：一打盾、一打嘲讽，恰好清掉 → 打脸 0。"""
        friendly = _player(board=[
            _card(name="a", attack=4, health=4),
            _card(name="b", attack=4, health=4),
        ])
        opp = _opp(
            health=10,
            board=[_card(name="圣盾嘲讽", attack=1, health=3, flags=["嘲讽", "圣盾"])],
        )
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_divine_shield_taunt_cleared_surplus_goes_face(self):
        """三只 4 攻：两次清圣盾嘲讽（4+4，过量 1），剩一只 4 攻打脸。"""
        friendly = _player(board=[
            _card(name="a", attack=4, health=4),
            _card(name="b", attack=4, health=4),
            _card(name="c", attack=4, health=4),
        ])
        opp = _opp(
            health=4,
            board=[_card(name="圣盾嘲讽", attack=1, health=3, flags=["嘲讽", "圣盾"])],
        )
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 4)
        self.assertTrue(check.lethal)

    def test_immune_taunt_blocks_attacks_forever(self):
        """免疫嘲讽无法被伤害清除：8+3 攻全被挡，打脸 0。"""
        friendly = _player(board=[
            _card(name="大怪", attack=8, health=8),
            _card(name="小怪", attack=3, health=3),
        ])
        opp = _opp(
            health=3,
            board=[_card(name="免疫嘲讽", attack=1, health=3, flags=["嘲讽", "免疫"])],
        )
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertTrue(check.taunt_blocked)
        self.assertFalse(check.lethal)

    def test_immune_taunt_spells_still_go_face(self):
        """免疫嘲讽挡不住打脸法术。"""
        spell = _card(name="火球术", cost=4, text="对一个角色造成 6 点伤害。")
        friendly = _player(mana=10, board=[_card(name="大怪", attack=8, health=8)], hand=[spell])
        opp = _opp(
            health=6,
            board=[_card(name="免疫嘲讽", attack=1, health=3, flags=["嘲讽", "免疫"])],
        )
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 6)
        self.assertTrue(check.taunt_blocked)
        self.assertTrue(check.lethal)


class BoardSlotConstraintTest(unittest.TestCase):
    """场上 7 个随从位满时，冲锋随从打不出（原实现误报）。

    竞品对齐：HDT 斩杀插件遵守随从位上限。
    """

    def test_charge_blocked_by_full_board(self):
        """7 个随从占满场面 → 手牌冲锋随从无法打出。"""
        board = [_card(name=f"占位{i}", attack=0, health=5, card_type="MINION") for i in range(7)]
        charger = _card(name="狼骑兵", attack=5, health=5, cost=5, flags=["冲锋"], card_type="MINION")
        friendly = _player(mana=5, board=board, hand=[charger])
        opp = _opp(health=5)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_charge_fits_with_six_minions(self):
        """6 个随从 → 冲锋随从可打出（第 7 位）。"""
        board = [_card(name=f"占位{i}", attack=0, health=5, card_type="MINION") for i in range(6)]
        charger = _card(name="狼骑兵", attack=5, health=5, cost=5, flags=["冲锋"], card_type="MINION")
        friendly = _player(mana=5, board=board, hand=[charger])
        opp = _opp(health=5)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 5)
        self.assertTrue(check.lethal)

    def test_non_minion_entities_do_not_occupy_slots(self):
        """英雄/英雄技能/武器不占随从位：6 随从 + 英雄 + 武器 → 仍可冲锋。"""
        board = [_card(name=f"占位{i}", attack=0, health=5, card_type="MINION") for i in range(6)]
        board += [
            _card(name="古尔丹", attack=2, health=30, card_type="HERO"),
            _card(name="奥金斧", attack=4, health=None, card_type="WEAPON"),
        ]
        charger = _card(name="狼骑兵", attack=5, health=5, cost=5, flags=["冲锋"], card_type="MINION")
        friendly = _player(mana=5, board=board, hand=[charger])
        opp = _opp(health=6)
        check = compute_lethal(_snap(friendly, opp))
        # 英雄 2 + 武器 4 + 冲锋 5 = 11，但只断言冲锋打得出去（>=5）
        self.assertGreaterEqual(check.available_damage, 5)

    def test_two_chargers_limited_by_one_slot(self):
        """只剩 1 个位、两只冲锋：只能打出一只（取伤害大的）。"""
        board = [_card(name=f"占位{i}", attack=0, health=5, card_type="MINION") for i in range(6)]
        big = _card(name="大冲锋", attack=5, health=5, cost=3, flags=["冲锋"], card_type="MINION")
        small = _card(name="小冲锋", attack=2, health=2, cost=1, flags=["冲锋"], card_type="MINION")
        friendly = _player(mana=5, board=board, hand=[big, small])
        opp = _opp(health=5)
        check = compute_lethal(_snap(friendly, opp))
        self.assertEqual(check.available_damage, 5)


class FatigueHintTest(unittest.TestCase):
    """对手牌库空 → 下回合抽牌受疲劳伤害（记牌器/斩杀提示联动）。"""

    def test_opponent_fatigue_hint_in_summary(self):
        """对手牌库 0、已疲劳 2 次 → 提示下回合受 3 点疲劳伤害。"""
        friendly = _player(board=[_card(name="小怪", attack=1, health=1)])
        opp = _opp(health=20)
        opp.deck_count = 0
        opp.fatigue = 2
        check = compute_lethal(_snap(friendly, opp))
        s = check.summary()
        self.assertIn("疲劳", s)
        self.assertIn("3", s)

    def test_no_fatigue_hint_when_deck_not_empty(self):
        """牌库未空 → 不提疲劳。"""
        friendly = _player(board=[_card(name="小怪", attack=1, health=1)])
        opp = _opp(health=20)
        opp.deck_count = 10
        opp.fatigue = 0
        check = compute_lethal(_snap(friendly, opp))
        self.assertNotIn("疲劳", check.summary())


if __name__ == "__main__":
    unittest.main()
