"""炉石教练测试共用工具（fixture 读取、卡牌库构建去重）。

原本各测试文件各自循环读 fixture 前 N 行（重复 4 份），统一收敛到这里。
"""

from pathlib import Path

from hscoach.cards import CardDatabase

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
