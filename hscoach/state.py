"""T5(05) 状态序列化：对局快照 → LLM 局面表示（含 D9 合法信息过滤）。

把 hslog 解析出的 Game 对象序列化成给 LLM 的结构化局面：
- 己方手牌（含卡名/费用/效果/CardID）
- 双方场面随从/英雄（攻血/关键词/效果）
- 双方英雄血量/护甲、当前法力
- 双方牌库剩余计数

D9 合法信息约束（硬约束，代码级断言保证）：
D9 是需求梳理阶段的第 9 条决策——只读合法可见信息（详见
.scratch/hearthstone-coach/spec.md 的 D9 节）：
- 对手手牌只暴露数量，绝不暴露具体卡牌
- 对手牌库内容不暴露
- 序列化时 assert：对手手牌实体若有 CardID，直接拒绝输出
- 友方玩家 id 可自动校准（见 detect_friendly_player_id），避免把
  对手手牌当成己方输出

设计参考：barnabys live.py snapshot_from_tree + format_snapshot 的精华
（卡牌文本内联、flags 显式化、只喂合法信息）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from hscoach.cards import Card, CardDatabase
from hearthstone.enums import CardType, GameTag, Zone

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
    "冲锋": GameTag.CHARGE,
    "突袭": GameTag.RUSH,
    "免疫": GameTag.IMMUNE,
    "休眠": GameTag.DORMANT,
    "无法攻击": GameTag.CANT_ATTACK,
    "已尽": GameTag.EXHAUSTED,  # 已行动/攻击过，本回合不能再用
    "不可被法术指定": GameTag.CANT_BE_TARGETED_BY_SPELLS,
}


@dataclass
class CardView:
    """局面中一张卡的精简视图（含注入的卡牌效果文本）。

    card_id 只对己方可见卡有意义：对手手牌不生成 CardView（只见数量），
    对手场上的卡是公开信息、带 CardID 合法。
    """

    card_id: str | None
    name: str
    cost: int | None
    attack: int | None
    health: int | None
    flags: list[str] = field(default_factory=list)
    text: str = ""  # 卡牌效果（来自卡牌库，非模型记忆）
    damaged: int = 0  # 受伤减血（在场随从上）
    card_type: str = ""  # 实体类型名（MINION/SPELL/HERO/WEAPON...，用于随从位等判断）
    card_class: str = ""  # 职业（来自卡牌库，用于奥秘池等按职业的推断）

    def to_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "cost": self.cost,
            "attack": self.attack,
            "health": self.health,
            "flags": self.flags,
            "text": self.text,
            "damaged": self.damaged or None,
            "card_type": self.card_type or None,
            "card_class": self.card_class or None,
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
    fatigue: int = 0  # 已受疲劳伤害次数（FATIGUE tag；牌库空时抽牌扣 fatigue+1）
    played_cards: list[CardView] = field(default_factory=list)  # 坟场（已出牌，公开）
    secrets: int = 0  # 场上奥秘数量（对手无 CardID，只计数）
    possible_secrets: list[str] = field(default_factory=list)  # 对手可能奥秘池（按职业）

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
            "fatigue": self.fatigue,
            "played_cards": [c.to_dict() for c in self.played_cards],
            "secrets": self.secrets,
            "possible_secrets": self.possible_secrets,
        }


@dataclass
class GameSnapshot:
    """一局对局在某一时刻的合法可见快照。"""

    turn: int
    current_player_id: int | None
    players: dict[int, PlayerView]  # player_id → view

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "current_player_id": self.current_player_id,
            "players": {pid: pv.to_dict() for pid, pv in self.players.items()},
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
    card_class = ""
    if card_id and db is not None:
        card: Card | None = db.get(card_id)
        if card is not None:
            name = card.name
            text = card.text
            card_class = card.card_class

    # 基础属性
    cost = tags.get(GameTag.COST)
    attack = tags.get(GameTag.ATK)
    health = tags.get(GameTag.HEALTH)
    damaged = tags.get(GameTag.DAMAGE, 0) or 0

    # 实体类型名（CardType 枚举名；未知/非法值回退空串）
    card_type = ""
    ct = tags.get(GameTag.CARDTYPE)
    if ct is not None:
        try:
            card_type = CardType(ct).name
        except ValueError:
            card_type = ""

    return CardView(
        card_id=card_id,
        name=name,
        cost=cost,
        attack=attack,
        health=health,
        flags=_extract_flags(tags),
        text=text,
        damaged=damaged,
        card_type=card_type,
        card_class=card_class,
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


def detect_friendly_player_id(game) -> int | None:
    """从对局推断友方玩家 id（日志自动校准，D9 防线）。

    原理：炉石客户端日志只对本地（友方）玩家的手牌写 CardID；对手手牌
    永远只有实体、无 CardID（这正是 D9 约束的前提）。因此"手牌含 CardID
    的玩家"即友方。

    Returns:
        唯一候选的玩家 id；手牌都为空（如开局调度阶段）或双方手牌都有
        CardID（观战等异常场景）时返回 None，表示暂无法判断。
    """
    candidates = []
    for player in game.players:
        pid = getattr(player, "player_id", None)
        if pid is None:
            continue
        hand = [
            e for e in game.in_zone(Zone.HAND)
            if e.tags.get(GameTag.CONTROLLER) == pid
        ]
        if any(getattr(e, "card_id", None) for e in hand):
            candidates.append(pid)
    if len(candidates) == 1:
        return candidates[0]
    return None


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

    # 当前回合与玩家
    turn = game.tags.get(GameTag.TURN, 0)
    # 当前玩家：部分日志在 GameEntity 上写 CURRENT_PLAYER（值是玩家 id）；
    # 另一些（如本仓库 fixture）只写在玩家实体上（value=0/1 置位）——
    # GameEntity 上没有 → 从玩家实体反推
    current_player_id = game.tags.get(GameTag.CURRENT_PLAYER)
    if current_player_id is None:
        for player in game.players:
            if player.tags.get(GameTag.CURRENT_PLAYER) == 1:
                current_player_id = getattr(player, "player_id", None)
                break

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

        # 疲劳计数（FATIGUE tag；牌库空时抽牌扣 fatigue+1）
        fatigue = player.tags.get(GameTag.FATIGUE, 0) or 0

        # 坟场（双方已出牌：公开信息，D9 只禁对手手牌不涉坟场）
        graveyard_entities = [
            e for e in game.in_zone(Zone.GRAVEYARD)
            if e.tags.get(GameTag.CONTROLLER) == pid
        ]
        played = [_entity_to_cardview(e, db) for e in graveyard_entities]

        # 奥秘：只计数（对手奥秘无 CardID，隐藏信息不可读）
        secrets = sum(
            1
            for e in game.in_zone(Zone.SECRET)
            if e.tags.get(GameTag.CONTROLLER) == pid
        )

        # 对手可能奥秘池：按英雄职业圈定标准年卡包内的奥秘（数据驱动）
        possible_secrets: list[str] = []
        if not is_friendly and secrets and db is not None:
            if hero_cv is not None and hero_cv.card_class:
                from hscoach.secrets import possible_secrets as pool

                possible_secrets = [
                    c.name for c in pool(db.iter_cards(), hero_cv.card_class)
                ]

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
            fatigue=fatigue,
            played_cards=played,
            secrets=secrets,
            possible_secrets=possible_secrets,
        )

    return GameSnapshot(
        turn=turn,
        current_player_id=current_player_id,
        players=players_view,
    )
