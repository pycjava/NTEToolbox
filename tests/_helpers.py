"""炉石教练测试共用工具（fixture 读取、卡牌库构建去重、局面构造）。

原本各测试文件各自循环读 fixture 前 N 行（重复 4 份），统一收敛到这里。
后来 lethal/coach/tracker 系列测试又各自重复定义 _card/_player/_opp/
_snap 构造器，同样收敛到这里（命名 make_*，各测试文件按需取别名）。
"""

from pathlib import Path

from hscoach.cards import CardDatabase
from hscoach.state import CardView, GameSnapshot, PlayerView

FIXTURE = Path(__file__).resolve().parent / "data" / "friendly_player_id_is_1.power.log"
CARD_CACHE_DIR = Path(__file__).resolve().parent / "_hs_cache"


def read_fixture_lines(n: int | None = None) -> list[str]:
    """读取 fixture 前 n 行（None=全部），返回含换行符的行列表。"""
    with FIXTURE.open(encoding="utf-8") as fp:
        lines = fp.readlines()
    return lines if n is None else lines[:n]


def card_db() -> CardDatabase:
    """构建卡牌库（用测试缓存目录，已构建过，离线可用）。"""
    db = CardDatabase(cache_dir=CARD_CACHE_DIR)
    db.build()
    return db


# ── 局面构造器（lethal / coach / tracker 系列测试共用）──────────────
# 友方默认：手牌可见、牌库 0；对手默认：手牌隐藏 4 张、牌库 0。
# 需要非空牌库（如验"不显示疲劳"）的用例按需显式传 deck_count。


def make_card(
    name: str = "",
    attack: int | None = None,
    health: int | None = None,
    cost: int | None = 0,
    flags: list[str] | None = None,
    text: str = "",
    card_id: str | None = None,
    card_type: str = "",
) -> CardView:
    """构造测试用 CardView。"""
    return CardView(
        card_id=card_id,
        name=name,
        cost=cost,
        attack=attack,
        health=health,
        flags=flags or [],
        text=text,
        card_type=card_type,
    )


def make_player(
    health: int = 30,
    armor: int = 0,
    mana: int = 10,
    max_mana: int = 10,
    hand: list | None = None,
    board: list | None = None,
    hand_is_hidden: bool = False,
    deck_count: int = 0,
    **extra,
) -> PlayerView:
    """构造友方 PlayerView。**extra 透传 fatigue/played_cards/secrets 等。"""
    return PlayerView(
        name="测试",
        hero=None,
        health=health,
        armor=armor,
        mana=mana,
        max_mana=max_mana,
        hand=hand or [],
        hand_is_hidden=hand_is_hidden,
        board=board or [],
        deck_count=deck_count,
        **extra,
    )


def make_opp(
    health: int = 30,
    armor: int = 0,
    board: list | None = None,
    deck_count: int = 0,
    **extra,
) -> PlayerView:
    """构造对手 PlayerView（手牌隐藏、只见数量）。**extra 透传同上。"""
    return PlayerView(
        name="对手",
        hero=None,
        health=health,
        armor=armor,
        mana=10,
        max_mana=10,
        hand=4,
        hand_is_hidden=True,
        board=board or [],
        deck_count=deck_count,
        **extra,
    )


def make_snapshot(friendly: PlayerView, opponent: PlayerView) -> GameSnapshot:
    """构造 GameSnapshot（友方当前回合）。"""
    return GameSnapshot(
        turn=6, current_player_id=1, players={1: friendly, 2: opponent}
    )
