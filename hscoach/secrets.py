"""T-S1 奥秘提示（竞品对齐：HDT / 网易盒子都有"猜奥秘"，本品原缺）。

对手打出的奥秘实体在日志里没有 CardID（与 D9 对手手牌同理：隐藏
信息不可读），只能按职业圈定候选池——标准年卡包内该职业的奥秘。
数据驱动：从卡牌库筛 type=SPELL、文本含"奥秘"、card_set 在
STANDARD_SETS 内的牌，不硬编码卡名（新卡包自动跟进）。

标准年卡包（Year of the Scarab 2026，2026-08 为准）：
- CORE                             核心系列（每年更新）
- EMERALD_DREAM                    Into the Emerald Dream（2025 扩展1）
- THE_LOST_CITY                    The Lost City of Un'Goro（2025 扩展2）
- TIME_TRAVEL                      Across the Timeways（2025 扩展3）
- CATACLYSM                        Cataclysm（2026 扩展1）
- ESCAPEFROM_VIOLET_HOLD           Escape from Violet Hold（2026 扩展2）

每年 4 月轮换时更新此常量（标准年 = 当年 + 前一年的卡包 + 核心）。

限制（已知差距，后续优化方向）：
- 只给候选池，不做 HDT 式"按触发事件逐个排除"的完整推理（需要监听
  攻击/法术事件流，规模大）。
- 双职业/发现生成的"非本职业奥秘"不在池内，UI 应注明"可能含生成
  奥秘"。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from hscoach.cards import Card

STANDARD_SETS: tuple[str, ...] = (
    "CORE",
    "EMERALD_DREAM",
    "THE_LOST_CITY",
    "TIME_TRAVEL",
    "CATACLYSM",
    "ESCAPEFROM_VIOLET_HOLD",
)


def possible_secrets(cards: Iterable["Card"], card_class: str) -> list["Card"]:
    """标准卡池里该职业可打出的奥秘（按费用升序）。

    Args:
        cards: 卡牌库全表（CardDatabase.iter_cards()）。
        card_class: 职业名（HUNTER/MAGE/PALADIN/ROGUE...，与
            HearthstoneJSON 的 cardClass 一致）。

    Returns:
        候选奥秘列表。职业无标准奥秘（如近年圣骑/盗贼）时为空。
    """
    if not card_class:
        return []
    result = []
    for c in cards:
        if c.type != "SPELL" or c.card_class != card_class:
            continue
        if c.card_set not in STANDARD_SETS:
            continue
        if "奥秘" not in c.text:
            continue
        result.append(c)
    result.sort(key=lambda c: c.cost)
    return result
