"""T-H1 对局结果与战绩统计（竞品对齐：HDT/盒子的对局记录/胜率统计）。

游戏结束时 Power.log 在【每个玩家实体】（PlayerOne/PlayerTwo 或数字
实体 id）上各写一次 tag=PLAYSTATE，值是枚举名（WON/LOST/TIED）——一方
WON、另一方 LOST。检测器按 friendly_player_id 取【友方】实体的终局值：
- history.jsonl：追加一行对局记录（结果/双方职业/回合数/时间）
- stats.json：聚合战绩（总场/胜负平/胜率/按职业/最近 N 局），原子写

前端盒子消费 stats.json 显示战绩；history.jsonl 留作后续复盘扩展。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

HISTORY_FILENAME = "history.jsonl"
STATS_FILENAME = "stats.json"
RECENT_LIMIT = 10

# 终局 PLAYSTATE 的枚举名 → 战绩（真实 Power.log 写枚举名 WON/LOST/TIED，
# 不是数字 4/5/6；进行中的 PLAYING/WINNING/LOSING 不在此表 → 被忽略）。
RESULT_MAP: dict[str, str] = {"WON": "win", "LOST": "loss", "TIED": "tie"}

# PLAYSTATE 写在【玩家实体】上（PlayerOne/PlayerTwo 或数字实体 id），值是
# 枚举名。注意：从不在 GameEntity 上、也不是数字——早期实现据此假设，
# 导致真实对局永不触发。
_PLAYSTATE_RE = re.compile(r"Entity=(\S+)\s+tag=PLAYSTATE\s+value=(\w+)")
# CREATE_GAME 块里的玩家声明：Player EntityID=2 PlayerID=1 → 实体↔玩家映射
_PLAYER_ENTITY_RE = re.compile(r"Player EntityID=(\d+)\s+PlayerID=(\d+)")
# 玩家实体名 ↔ 实体 id 是炉石协议常量（GameEntity=1、先手=2、后手=3）
_NAME_TO_ENTITY_ID = {"PlayerOne": 2, "PlayerTwo": 3}


class GameResultDetector:
    """从原始日志行检测对局终局结果（正则，极快，无需 hslog 解析）。

    真实日志在【每个玩家实体】上各写一次 PLAYSTATE（一方 WON、另一方
    LOST）。本检测器按 friendly_player_id 取【友方】实体的终局值，避免
    "取首个命中"把对手结果记成友方（约一半对局记反）。每局只触发一次；
    CREATE_GAME 或 reset() 开启下一局。

    friendly_player_id 可热更新（日志自动校准后，__main__ 同步刷新此属性）。
    """

    def __init__(self, friendly_player_id: int = 1) -> None:
        self.friendly_player_id = friendly_player_id
        self._fired = False
        self._entity_to_player: dict[int, int] = {}

    def feed(self, lines: list[str]) -> list[str]:
        """喂入原始日志行，返回本次检测到的【友方】终局结果（win/loss/tie）。"""
        results: list[str] = []
        for line in lines:
            if "CREATE_GAME" in line:
                self._fired = False  # 新对局
                self._entity_to_player.clear()
                continue
            if "Player EntityID=" in line:
                m = _PLAYER_ENTITY_RE.search(line)
                if m:
                    self._entity_to_player[int(m.group(1))] = int(m.group(2))
                continue
            if self._fired or "tag=PLAYSTATE" not in line:
                continue
            m = _PLAYSTATE_RE.search(line)
            if not m:
                continue
            token, value = m.group(1), m.group(2)
            if value not in RESULT_MAP:  # PLAYING/WINNING/LOSING 等非终局
                continue
            pid = self._resolve_player_id(token)
            if pid is None or pid != self.friendly_player_id:
                continue  # 只记友方实体的结果，忽略对手那条
            self._fired = True
            results.append(RESULT_MAP[value])
        return results

    def _resolve_player_id(self, token: str) -> int | None:
        """把 PLAYSTATE 行的 Entity 令牌解析成玩家 id。

        数字令牌当实体 id；名字（PlayerOne/Two）按协议常量转实体 id；
        再用本局 CREATE_GAME 建立的映射转玩家 id，缺映射时回退 eid-1
        （实体 2=玩家1、3=玩家2，协议常量）。
        """
        if token.isdigit():
            eid = int(token)
        else:
            eid = _NAME_TO_ENTITY_ID.get(token)
            if eid is None:
                return None
        return self._entity_to_player.get(eid, eid - 1)

    def reset(self) -> None:
        self._fired = False
        self._entity_to_player.clear()


def _atomic_write_json(path: Path, payload: dict) -> None:
    """原子写 JSON（tmp + os.replace，读者永不看到半写状态）。"""
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".stats_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _aggregate(history_path: Path) -> dict:
    """从 history.jsonl 聚合战绩。文件缺失/损坏时返回空战绩。"""
    stats: dict = {
        "total": 0,
        "wins": 0,
        "losses": 0,
        "ties": 0,
        "winrate_pct": 0.0,
        "by_class": {},
        "recent": [],
    }
    if not history_path.exists():
        return stats
    try:
        entries = [
            json.loads(line)
            for line in history_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError):
        return stats  # 损坏的历史不致命，从头开始
    for e in entries:
        stats["total"] += 1
        result = e.get("result")
        if result == "win":
            stats["wins"] += 1
        elif result == "loss":
            stats["losses"] += 1
        else:
            stats["ties"] += 1
        cls = e.get("friendly_class") or "未知"
        bucket = stats["by_class"].setdefault(cls, {"wins": 0, "losses": 0})
        if result == "win":
            bucket["wins"] += 1
        elif result == "loss":
            bucket["losses"] += 1
    stats["recent"] = entries[-RECENT_LIMIT:]
    if stats["total"]:
        stats["winrate_pct"] = round(stats["wins"] / stats["total"] * 100, 1)
    return stats


def record_result(
    publish_dir: Path,
    result: str,
    friendly_class: str,
    opponent_class: str,
    turns: int,
) -> dict:
    """记录一局结果：追加 history.jsonl + 重写 stats.json。

    Returns:
        聚合后的战绩 dict（前端可直接消费）。
    """
    publish_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "result": result,
        "friendly_class": friendly_class or "未知",
        "opponent_class": opponent_class or "未知",
        "turns": turns,
    }
    history_path = publish_dir / HISTORY_FILENAME
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    stats = _aggregate(history_path)
    _atomic_write_json(publish_dir / STATS_FILENAME, stats)
    return stats
