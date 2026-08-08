"""T3(03) 卡牌知识库。

从 HearthstoneJSON 拉取简体中文全卡数据，构建本地卡牌库：
- 按 CardID 查卡名、效果文本（清洗后）、费用、攻击/生命等
- 效果文本清洗：移除 HearthstoneJSON 的标记符号（<b>/<i>/$/#/[x]/{N}）
- 渲染图 URL 生成（art.hearthstonejson.com，按需下载缓存）

设计参考：barnabys live.py card_text() 的清洗逻辑。
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import httpx

HEARTHSTONEJSON_CARDS_URL = (
    "https://api.hearthstonejson.com/v1/latest/{locale}/cards.collectible.json"
)
HEARTHSTONEJSON_ALL_CARDS_URL = (
    "https://api.hearthstonejson.com/v1/latest/{locale}/cards.json"
)
RENDER_IMAGE_URL = (
    "https://art.hearthstonejson.com/v1/render/latest/{locale}/512x/{card_id}.png"
)
DEFAULT_LOCALE = "zhCN"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "data"

# HearthstoneJSON 文本标记清洗：
#   <b>...</b> / <i>...</i>  → 去标签（粗体/斜体是视觉标记）
#   $                        → 段落分隔，转换行
#   #                        → 项目符号，转 "• "
#   [x]                      → 卡牌悬浮锚点，删除
#   {0}/{1}/..               → 占位符，转 X（barnabys 做法）
#   \n 连续空行              → 压缩
_TAG_RE = re.compile(r"</?[bi]>")
_PLACEHOLDER_RE = re.compile(r"\{\d+}")
_WHITESPACE_RE = re.compile(r"\n{3,}")


def clean_text(raw: str | None) -> str:
    """清洗 HearthstoneJSON 卡牌文本标记成干净的中文可读文本。"""
    if not raw:
        return ""
    text = _TAG_RE.sub("", raw)
    text = text.replace("$", "\n").replace("#", "• ").replace("[x]", "")
    text = _PLACEHOLDER_RE.sub("X", text)
    text = _WHITESPACE_RE.sub("\n\n", text)
    return text.strip()


@dataclass(frozen=True)
class Card:
    """一张炉石卡牌的精简视图（只保留教练需要的字段）。"""

    id: str
    name: str
    text: str  # 清洗后的效果文本
    cost: int
    attack: int | None
    health: int | None
    type: str  # MINION / SPELL / WEAPON / HERO / ...
    card_class: str


class CardDatabase:
    """本地卡牌库。首次构建从 HearthstoneJSON 拉取并缓存为 JSON 文件。

    线程安全（构建一次后只读）。查询不依赖网络（离线可用）。
    """

    def __init__(self, cache_dir: Path | None = None, locale: str = DEFAULT_LOCALE):
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self._locale = locale
        self._cards: dict[str, Card] = {}
        self._lock = threading.Lock()
        self._loaded = False

    @property
    def cache_path(self) -> Path:
        return self._cache_dir / f"cards.{self._locale}.json"

    @property
    def all_cards_cache_path(self) -> Path:
        return self._cache_dir / f"cards.all.{self._locale}.json"

    def build(self, force: bool = False) -> None:
        """构建卡牌库。优先用本地缓存；force=True 或无缓存时从网络拉取。

        拉取两份数据：
        - cards.collectible.json：收集卡（玩家可组的卡）
        - cards.json：全卡（含非收集卡如教程卡 TUTR_、英雄技能等）
        合并后教程卡等也能查到卡名和效果。
        """
        with self._lock:
            if self._loaded and not force:
                return
            if force or not self.cache_path.exists() or not self.all_cards_cache_path.exists():
                self._download()
            self._load_from_cache()
            self._loaded = True

    def _download(self) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=120, headers={"User-Agent": "NTEToolbox/0.1"}) as client:
            collectible = client.get(
                HEARTHSTONEJSON_CARDS_URL.format(locale=self._locale)
            ).json()
            all_cards = client.get(
                HEARTHSTONEJSON_ALL_CARDS_URL.format(locale=self._locale)
            ).json()
        # 原子写两份
        for data, path in [
            (collectible, self.cache_path),
            (all_cards, self.all_cards_cache_path),
        ]:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)

    def _load_from_cache(self) -> None:
        cards: dict[str, Card] = {}

        def load_entries(raw: list, overwrite: bool) -> None:
            for entry in raw:
                cid = entry.get("id")
                if not cid:
                    continue
                if cid in cards and not overwrite:
                    continue  # 收集卡优先，不覆盖
                cards[cid] = Card(
                    id=cid,
                    name=entry.get("name", cid),
                    text=clean_text(entry.get("text")),
                    cost=entry.get("cost", 0),
                    attack=entry.get("attack"),
                    health=entry.get("health"),
                    type=entry.get("type", ""),
                    card_class=entry.get("cardClass", ""),
                )

        # 先加载全卡（含教程卡等非收集卡），再用收集卡覆盖
        if self.all_cards_cache_path.exists():
            load_entries(json.loads(self.all_cards_cache_path.read_text(encoding="utf-8")), overwrite=True)
        load_entries(json.loads(self.cache_path.read_text(encoding="utf-8")), overwrite=True)
        self._cards = cards

    def get(self, card_id: str) -> Card | None:
        """按 CardID 查卡。未构建返回 None。"""
        if not self._loaded:
            self.build()
        return self._cards.get(card_id)

    def __contains__(self, card_id: str) -> bool:
        if not self._loaded:
            self.build()
        return card_id in self._cards

    def __len__(self) -> int:
        if not self._loaded:
            self.build()
        return len(self._cards)

    def render_image_url(self, card_id: str) -> str:
        """渲染图 URL（含卡名/费用/描述的完整卡图，简中）。"""
        return RENDER_IMAGE_URL.format(locale=self._locale, card_id=card_id)
