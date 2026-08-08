"""T2(04) 炉石日志解析：Power.log → 对局快照。

封装 hslog 解析，内含两个踩坑硬通货（来自 barnabys 精读）：
1. 每局一个全新 LogParser：玩家 id 跨局会重排，单 parser 喂多局会抛
   InconsistentPlayerIdError 整文件全丢。用 CREATE_GAME 边界切分。
2. 容错：炉石偶发写坏包（空 CardID 等），坏行/坏包跳过不卡死整个解析。

输入：Power.log 文本行（带或不带 [Power] 前缀均可，本模块剥离前缀）。
输出：Game 对象列表（来自 hslog.export.EntityTreeExporter.game）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from hearthstone.enums import GameTag
from hslog.parser import LogParser

logger = logging.getLogger(__name__)


def _disable_hearthstone_cardxml() -> None:
    """硬化：阻止 hslog 导出时隐式下载 HearthSim 卡牌数据库。

    背景（真实踩坑）：hearthstone.cardxml.load/load_dbf 在导出遇到第一张带
    TRANSFORMED_FROM_CARD 标记的卡时会触发，若未安装 hearthstone_data 包则
    从 api.hearthstonejson.com 下载整个 CardDefs.xml（几十 MB，带重试），
    在无外网/慢网环境会把导出线程挂死数分钟——对局中教练直接失联。

    我们用自己的卡牌库（hscoach.cards，效果文本已注入序列化层），hslog
    导出的 EntityTreeExporter 只用 db.get() 查 TRANSFORMED_FROM_CARD 的
    初始卡（查不到仅导致 initial_card_id 为空，无害），从不依赖 base_tags。
    因此把两份加载函数替换为空库即可，功能无损且网络依赖归零。
    """
    import hearthstone.cardxml as cardxml

    cardxml.load = lambda *args, **kwargs: ({}, None)
    cardxml.load_dbf = lambda *args, **kwargs: ({}, None)


_disable_hearthstone_cardxml()

# hslog read_line 期望的格式是 "D <ts> GameState.DebugPrintPower() - ..."
# 真实 Power.log 文件每行带 "[Power]" 频道前缀，需剥离
_POWER_PREFIX = "[Power] "


def _strip_power_prefix(line: str) -> str:
    """剥离 Power.log 行的 [Power] 频道前缀，还原 hslog 期望的原始格式。"""
    idx = line.find(_POWER_PREFIX)
    if idx >= 0:
        return line[idx + len(_POWER_PREFIX) :]
    return line


@dataclass
class ParseResult:
    """一次解析的产出：成功解析的对局 + 被跳过的坏行数。

    packet_trees 与 games 一一对应（hslog 的 PacketTree 原始树）。
    保留它用于轻量推断（如 FriendlyPlayerExporter 推断友方玩家），
    无需再次全量解析。
    """

    games: list = field(default_factory=list)
    packet_trees: list = field(default_factory=list)
    skipped_lines: int = 0
    skipped_packets: int = 0


def parse_power_log(lines: Iterable[str]) -> ParseResult:
    """解析 Power.log 行流，返回 ParseResult。

    策略：
    - 按 CREATE_GAME 边界切分，每局重建 LogParser（避免跨局玩家 id 重排崩溃）。
    - 坏行（格式不符）计数并跳过，不抛异常。
    - 导出时用 tolerate_missing_entities=True（hslog 原生支持的容错，等价于
      barnabys 的 TolerantExporter），吞掉坏包。
    """
    result = ParseResult()
    current_parser: LogParser | None = None
    finished_parsers: list[LogParser] = []

    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        line = _strip_power_prefix(line)

        # 检测 CREATE_GAME 边界 → 开新局
        is_create = "CREATE_GAME" in line and "DebugPrintPower" in line
        if is_create:
            if current_parser is not None:
                finished_parsers.append(current_parser)
            current_parser = LogParser()

        if current_parser is None:
            # CREATE_GAME 之前的行忽略（hslog 默认行为）
            continue

        try:
            current_parser.read_line(line)
        except Exception as e:  # 坏行容错，记录跳过
            result.skipped_lines += 1
            logger.debug("跳过无法解析的日志行: %s | 行: %r", e, line[:80])

    if current_parser is not None:
        finished_parsers.append(current_parser)

    # 每局独立导出
    for parser in finished_parsers:
        for packet_tree in parser.games:
            try:
                exporter = packet_tree.export()
                game = getattr(exporter, "game", None)
                if game is not None:
                    result.games.append(game)
                    result.packet_trees.append(packet_tree)
            except Exception as e:  # 坏包容错
                result.skipped_packets += 1
                logger.warning("跳过无法导出的对局: %s", e)

    return result


def parse_power_log_file(path) -> ParseResult:
    """从文件解析。path 可为 str 或 PathLike。"""
    from pathlib import Path

    p = Path(path)
    with p.open(encoding="utf-8") as fp:
        return parse_power_log(fp)
