"""T5(05) 状态序列化：对局快照 → LLM 局面表示（含 D9 合法信息过滤）。

把 hslog 解析出的 Game 对象序列化成给 LLM 的结构化局面：
- 己方手牌（含卡名/费用/效果）
- 双方场面随从/英雄（攻血/关键词/效果）
- 双方英雄血量/护甲、当前法力
- 己方牌库剩余计数
- 对手出牌史（已揭示的）

D9 合法信息约束（硬约束，代码级断言保证）：
- 对手手牌只暴露数量，绝不暴露具体卡牌
- 对手牌库内容不暴露
- 序列化时 assert：对手手牌实体若有 CardID，直接拒绝输出

设计参考：barnabys live.py snapshot_from_tree + format_snapshot 的精华
（卡牌文本内联、flags 显式化、只喂合法信息）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from hscoach.cards import Card, CardDatabase
from hearthstone.enums import GameTag, Zone

logger = logging.getLogger(__name__)

# 需要显式提取的关键词 tags（参考 barnabys live.py flags 列表）
_FLAG_TAGS: dict[str, GameTag] = {
    "嘲讽": GameTag.TAUNT,
    "圣盾": GameTag.DIVINE_SHIELD,
    "风怒": GameTag.WINDFURY,
    "剧毒": GameTag.POISONOUS,
    "复生": GameTag.REBORN,
    "冻结": GameTag.FROZEN,
    "潜行": GameTag.STEALTH,
    "吸血": GameTag.LIFESTEAL,
    "突袭": GameTag.RUSH,
    "免疫": GameTag.IMMUNE,
    "休眠": GameTag.DORMANT,
    "无法攻击": GameTag.CANT_ATTACK,
}


@dataclass
class CardView:
    """局面中一张卡的精简视图（含注入的卡牌效果文本）。"""

    card_id: str | None
    name: str
    cost: int | None
    attack: int | None
    health: int | None
    flags: list[str] = field(default_factory=list)
    text: str = ""  # 卡牌效果（来自卡牌库，非模型记忆）
    damage: int = 0  # 受伤减血（在场随从上）

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "cost": self.cost,
            "attack": self.attack,
            "health": self.health,
            "flags": self.flags,
            "text": self.text,
            "damaged": self.damage or None,
        }


@dataclass
class PlayerView:
    """一个玩家的合法可见视图。"""

    name: str
    hero: CardView | None
    health: int
    armor: int
    mana: int
    max_mana: int
    hand: list[CardView] | int  # 己方是列表，对手是数量
    hand_is_hidden: bool  # True=对手（只见数量）
    board: list[CardView]
    deck_count: int

    def to_dict(self) -> dict:
        hand: object
        if self.hand_is_hidden:
            hand = {"count": self.hand}  # type: ignore[arg-type]
        else:
            hand = [c.to_dict() for c in self.hand]  # type: ignore[list-item]
        return {
            "name": self.name,
            "health": self.health,
            "armor": self.armor,
            "mana": self.mana,
            "max_mana": self.max_mana,
            "hand": hand,
            "board": [c.to_dict() for c in self.board],
            "deck_count": self.deck_count,
        }


@dataclass
class GameSnapshot:
    """一局对局在某一时刻的合法可见快照。"""

    turn: int
    current_player_id: int | None
    players: dict[int, PlayerView]  # player_id → view
    opponent_played: list[CardView] = field(default_factory=list)  # 对手已打出的牌

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "current_player_id": self.current_player_id,
            "players": {pid: pv.to_dict() for pid, pv in self.players.items()},
            "opponent_played": [c.to_dict() for c in self.opponent_played],
        }


def _extract_flags(tags: dict) -> list[str]:
    """从 entity tags 提取显式关键词列表。"""
    flags = []
    for label, gtag in _FLAG_TAGS.items():
        if tags.get(gtag):
            flags.append(label)
    return flags


def _entity_to_cardview(entity, db: CardDatabase | None) -> CardView:
    """把 hslog entity 转成 CardView，注入卡牌效果文本（来自卡牌库）。"""
    tags = entity.tags
    card_id = getattr(entity, "card_id", None)
    name = card_id or "未知卡牌"
    text = ""
    if card_id and db is not None:
        card: Card | None = db.get(card_id)
        if card is not None:
            name = card.name
            text = card.text

    # 基础属性
    cost = tags.get(GameTag.COST)
    attack = tags.get(GameTag.ATK)
    health = tags.get(GameTag.HEALTH)
    damage = tags.get(GameTag.DAMAGE, 0) or 0

    return CardView(
        card_id=card_id,
        name=name,
        cost=cost,
        attack=attack,
        health=health,
        flags=_extract_flags(tags),
        text=text,
        damage=damage,
    )


def _assert_no_opponent_hand_leak(entities_in_hand: list, player_id: int) -> None:
    """D9 代码级保证：对手手牌实体不应带 CardID（已揭示的会被移出该区）。

    如果发现带 CardID 的对手手牌实体，说明我们的过滤逻辑有漏洞，
    直接拒绝序列化（fail loud，不让隐藏信息悄悄泄露）。
    """
    for ent in entities_in_hand:
        cid = getattr(ent, "card_id", None)
        if cid:
            raise AssertionError(
                f"D9 违规：玩家 {player_id}（对手）的手牌实体 {getattr(ent, 'id', '?')} "
                f"带 CardID={cid!r}，隐藏信息可能泄露。拒绝序列化。"
            )


def serialize_game(game, friendly_player_id: int, db: CardDatabase | None = None) -> GameSnapshot:
    """把 hslog Game 序列化成合法可见快照。

    Args:
        game: hslog 解析出的 Game 对象
        friendly_player_id: 友方玩家 id（1 或 2）
        db: 卡牌库（用于注入效果文本），None 则不注入

    Returns:
        GameSnapshot，其中对手手牌只有数量、无具体卡牌。

    Raises:
        AssertionError: D9 检测到对手手牌可能泄露 CardID
    """
    players_view: dict[int, PlayerView] = {}
    opponent_played: list[CardView] = []

    # 当前回合与玩家
    turn = game.tags.get(GameTag.TURN, 0)
    current_player_id = game.tags.get(GameTag.CURRENT_PLAYER)

    for player in game.players:
        pid = getattr(player, "player_id", None)
        if pid is None:
            continue
        is_friendly = pid == friendly_player_id

        # 英雄实体
        hero_entity_id = player.tags.get(GameTag.HERO_ENTITY)
        hero_cv = None
        health = player.tags.get(GameTag.HEALTH, 30) or 30
        armor = player.tags.get(GameTag.ARMOR, 0) or 0
        mana = player.tags.get(GameTag.RESOURCES, 0) or 0
        max_mana = player.tags.get(GameTag.MAXRESOURCES, 10) or 10

        if hero_entity_id is not None:
            hero_ent = game.find_entity_by_id(hero_entity_id)
            if hero_ent is not None:
                hero_cv = _entity_to_cardview(hero_ent, db)
                # 英雄血量从 entity tag 取（更准）
                ent_hp = hero_ent.tags.get(GameTag.HEALTH)
                if ent_hp is not None:
                    health = ent_hp - hero_ent.tags.get(GameTag.DAMAGE, 0)

        # 手牌：in_zone(HAND) 给该 zone 所有实体，按 CONTROLLER 过滤
        hand_entities = [
            e for e in game.in_zone(Zone.HAND)
            if e.tags.get(GameTag.CONTROLLER) == pid
        ]
        if is_friendly:
            hand = [_entity_to_cardview(e, db) for e in hand_entities]
            hand_is_hidden = False
        else:
            # D9：对手手牌只见数量。先断言没有泄露 CardID
            _assert_no_opponent_hand_leak(hand_entities, pid)
            hand = len(hand_entities)
            hand_is_hidden = True

        # 场上随从（PLAY zone，排除英雄）
        board_entities = [
            e for e in game.in_zone(Zone.PLAY)
            if e.tags.get(GameTag.CONTROLLER) == pid
            and e.tags.get(GameTag.CARDTYPE) != 2  # HERO type=2 排除
        ]
        board = [_entity_to_cardview(e, db) for e in board_entities]

        # 牌库计数
        deck_entities = [
            e for e in game.in_zone(Zone.DECK)
            if e.tags.get(GameTag.CONTROLLER) == pid
        ]
        deck_count = len(deck_entities)

        players_view[pid] = PlayerView(
            name=getattr(player, "name", None) or f"玩家{pid}",
            hero=hero_cv,
            health=health,
            armor=armor,
            mana=mana,
            max_mana=max_mana,
            hand=hand,
            hand_is_hidden=hand_is_hidden,
            board=board,
            deck_count=deck_count,
        )

    return GameSnapshot(
        turn=turn,
        current_player_id=current_player_id,
        players=players_view,
        opponent_played=opponent_played,
    )
