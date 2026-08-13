"""T5(05)-S1 记牌器序列化测试：疲劳计数 / 双方已出牌（坟场）/ 奥秘提示。

竞品差距：盒子"双方坟场"、HDT/盒子"猜奥秘"、各家的疲劳计数，本品
原都缺。全部来自公开信息（坟场=已揭示的牌，D9 合规）。

- 真实 fixture：GRAVEYARD 有 2 张 TB_Superfriends001（双方各 1 张）
- 合成 Game：FATIGUE tag、SECRET zone 实体计数、对手奥秘池（按英雄
  职业，数据驱动）
"""

import logging
import unittest
from types import SimpleNamespace

logging.disable(logging.WARNING)

from hearthstone.enums import CardType, GameTag, Zone
from hscoach.log_parser import parse_power_log
from hscoach.state import serialize_game
from tests._helpers import card_db, read_fixture_lines


class _FakeEntity:
    """最小 hslog 实体假件：serialize_game 只用 tags + card_id。

    tags 的键必须用 GameTag 枚举（与真实 hslog 一致，字符串键查不到）。
    """

    def __init__(self, eid, card_id=None, tags=None):
        self.id = eid
        self.card_id = card_id
        self.tags = tags or {}


class _FakeGame:
    """最小 hslog Game 假件：players / tags / in_zone / find_entity_by_id。"""

    def __init__(self, players):
        self.players = players
        self.tags = {}
        self._by_zone: dict = {}
        self._by_id: dict = {}

    def in_zone(self, zone):
        return self._by_zone.get(zone, [])

    def find_entity_by_id(self, eid):
        return self._by_id.get(eid)

    def add(self, zone, entity):
        self._by_zone.setdefault(zone, []).append(entity)
        self._by_id[entity.id] = entity


def _fake_player(pid, hero_entity=None, fatigue=0):
    return SimpleNamespace(
        player_id=pid,
        name=f"玩家{pid}",
        tags={
            GameTag.HERO_ENTITY: hero_entity,
            GameTag.HEALTH: 30,
            GameTag.ARMOR: 0,
            GameTag.RESOURCES: 5,
            GameTag.MAXRESOURCES: 6,
            GameTag.FATIGUE: fatigue,
        },
    )


def _hero_entity(eid, controller, card_id):
    return _FakeEntity(eid, card_id, tags={
        GameTag.CONTROLLER: controller,
        GameTag.CARDTYPE: CardType.HERO,
        GameTag.HEALTH: 30,
        GameTag.DAMAGE: 0,
    })


def _build_game():
    """对手=法师（HERO_08）、双方都有坟场牌与奥秘的合成对局。"""
    game = _FakeGame([_fake_player(1, hero_entity=10, fatigue=1),
                      _fake_player(2, hero_entity=20, fatigue=0)])
    game.tags[GameTag.TURN] = 7
    game.tags[GameTag.CURRENT_PLAYER] = 1
    game.add(Zone.PLAY, _hero_entity(10, 1, "HERO_09"))  # 我方牧师英雄
    game.add(Zone.PLAY, _hero_entity(20, 2, "HERO_08"))  # 对手法师英雄
    # 坟场：双方各一张已揭示的牌（公开信息）
    game.add(Zone.GRAVEYARD, _FakeEntity(101, "CS2_029", tags={
        GameTag.CONTROLLER: 1, GameTag.CARDTYPE: CardType.SPELL}))
    game.add(Zone.GRAVEYARD, _FakeEntity(102, "CS2_024", tags={
        GameTag.CONTROLLER: 2, GameTag.CARDTYPE: CardType.SPELL}))
    # 奥秘：对手 2 个（无 CardID——隐藏信息），我方 1 个
    game.add(Zone.SECRET, _FakeEntity(201, None, tags={
        GameTag.CONTROLLER: 2, GameTag.CARDTYPE: CardType.SPELL}))
    game.add(Zone.SECRET, _FakeEntity(202, None, tags={
        GameTag.CONTROLLER: 2, GameTag.CARDTYPE: CardType.SPELL}))
    game.add(Zone.SECRET, _FakeEntity(203, None, tags={
        GameTag.CONTROLLER: 1, GameTag.CARDTYPE: CardType.SPELL}))
    return game


class GraveyardSerializationTest(unittest.TestCase):
    """双方已出牌（坟场）：真实 fixture 双方各 1 张。"""

    @classmethod
    def setUpClass(cls):
        result = parse_power_log(read_fixture_lines(4000))
        cls.game = result.games[0]
        cls.db = card_db()

    def test_played_cards_serialized_for_both_players(self):
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        for pid in (1, 2):
            played = snap.players[pid].played_cards
            self.assertEqual(len(played), 1, f"玩家 {pid} 坟场应有 1 张牌")
            self.assertEqual(played[0].card_id, "TB_Superfriends001")

    def test_played_cards_in_dict_output(self):
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        d = snap.to_dict()
        opp_played = d["players"][2]["played_cards"]
        self.assertEqual(len(opp_played), 1)
        self.assertIn("card_id", opp_played[0])
        self.assertEqual(opp_played[0]["card_id"], "TB_Superfriends001")

    def test_played_cards_is_public_not_hidden(self):
        """对手已出牌是公开信息（已打出/已揭示），D9 只禁对手手牌。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        self.assertTrue(snap.players[2].hand_is_hidden)  # 手牌仍只见数量
        self.assertGreater(len(snap.players[2].played_cards), 0)  # 已出牌可见


class FatigueSerializationTest(unittest.TestCase):
    """疲劳计数：FATIGUE tag 序列化。"""

    def test_fatigue_serialized(self):
        snap = serialize_game(_build_game(), friendly_player_id=1, db=None)
        self.assertEqual(snap.players[1].fatigue, 1)
        self.assertEqual(snap.players[2].fatigue, 0)

    def test_fatigue_default_zero_when_tag_missing(self):
        """FATIGUE tag 缺失 → 0（不崩）。"""
        game = _FakeGame([_fake_player(1, hero_entity=10),
                          _fake_player(2, hero_entity=20)])
        game.tags[GameTag.TURN] = 1
        game.add(Zone.PLAY, _hero_entity(10, 1, "HERO_09"))
        game.add(Zone.PLAY, _hero_entity(20, 2, "HERO_08"))
        snap = serialize_game(game, friendly_player_id=1, db=None)
        self.assertEqual(snap.players[1].fatigue, 0)


class SecretSerializationTest(unittest.TestCase):
    """奥秘：数量（双方）+ 对手可能奥秘池（按英雄职业）。"""

    @classmethod
    def setUpClass(cls):
        cls.db = card_db()

    def test_secret_counts(self):
        snap = serialize_game(_build_game(), friendly_player_id=1, db=self.db)
        self.assertEqual(snap.players[1].secrets, 1)
        self.assertEqual(snap.players[2].secrets, 2)

    def test_opponent_possible_secrets_from_hero_class(self):
        """对手英雄 HERO_08（法师）→ 可能奥秘 = 法师标准奥秘池。"""
        snap = serialize_game(_build_game(), friendly_player_id=1, db=self.db)
        names = snap.players[2].possible_secrets
        self.assertTrue(names, "法师标准奥秘池不应为空")
        # 核心奥秘稳定存在（历年核心卡池）
        self.assertIn("法术反制", names)
        self.assertIn("寒冰护体", names)

    def test_friendly_side_has_no_possible_secrets(self):
        """己方知道自己的奥秘，无需候选池。"""
        snap = serialize_game(_build_game(), friendly_player_id=1, db=self.db)
        self.assertEqual(snap.players[1].possible_secrets, [])

    def test_no_db_no_possible_secrets(self):
        """无卡牌库 → 候选池为空，不崩。"""
        snap = serialize_game(_build_game(), friendly_player_id=1, db=None)
        self.assertEqual(snap.players[2].possible_secrets, [])

    def test_secret_count_in_dict_output(self):
        snap = serialize_game(_build_game(), friendly_player_id=1, db=self.db)
        d = snap.to_dict()
        self.assertEqual(d["players"][2]["secrets"], 2)
        self.assertIn("possible_secrets", d["players"][2])


if __name__ == "__main__":
    unittest.main()
