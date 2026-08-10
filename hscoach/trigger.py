"""T7(07) 回合触发器 + 建议发布。

从日志流检测"轮到友方玩家回合"事件，触发 LLM 教练生成建议，
以原子写 JSON 文件（advice.json）方式发布供 UI 消费。

触发检测：监听 TAG_CHANGE ... tag=TURN value=N（回合数递增，写在
GameEntity 上）+ CURRENT_PLAYER 指向友方玩家（写在玩家实体上，实体名
PlayerOne/PlayerTwo 或数字实体 id 两种形态）。每当 TURN tag 递增且当前
是友方回合，触发一次。

发布契约（advice.json，语言无关，三期 C# WPF 可零成本复用）：
    {
      "turn": 5,
      "timestamp": "2026-08-08T12:34:56",
      "advice": { ... Advice.to_dict() ... }
    }
原子写：先写临时文件再 os.replace，读者永不看到半写状态。

盒子数据源（game_state.json）：与 advice.json 同契约的实时对局快照
（turn/current_player_id/friendly_player_id/players），已过 D9 过滤。
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from hscoach.coach import Advice, LLMClient, get_advice
from hscoach.state import GameSnapshot, serialize_game
from hscoach.cards import CardDatabase

logger = logging.getLogger(__name__)

ADVICE_FILENAME = "advice.json"
GAME_STATE_FILENAME = "game_state.json"  # 盒子（记牌器）数据源，实时对局快照

# 增量检测用的正则：从原始日志行快速提取回合信息，无需 hslog 全量解析
# 回合数写在 GameEntity 上：TAG_CHANGE Entity=GameEntity tag=TURN value=N
_TURN_RE = re.compile(r"tag=TURN\s+value=(\d+)")
# 当前玩家写在玩家实体上，实体有两种形态（名字/数字 id）：
#   TAG_CHANGE Entity=PlayerTwo tag=CURRENT_PLAYER value=1
#   TAG_CHANGE Entity=3 tag=CURRENT_PLAYER value=1
# value 是 0/1 布尔置位，不是玩家 id！（踩坑：曾误把 value 当玩家 id，
# 导致 friendly=2 永不触发、friendly=1 对方回合也误触发）
_CURRENT_PLAYER_RE = re.compile(
    r"Entity=(PlayerOne|PlayerTwo|\d+)\s+tag=CURRENT_PLAYER\s+value=(\d+)"
)
# CREATE_GAME 块里的玩家声明：Player EntityID=2 PlayerID=1 → 实体 id↔玩家 id
_PLAYER_ENTITY_RE = re.compile(r"Player EntityID=(\d+) PlayerID=(\d+)")
# 玩家实体名 ↔ 实体 id 是炉石协议常量（GameEntity=1、先手=2、后手=3）
_NAME_TO_ENTITY_ID = {"PlayerOne": 2, "PlayerTwo": 3}


def _is_new_friendly_turn(
    turn: int,
    current_player_id: int | None,
    friendly_player_id: int,
    last_turn: int,
) -> bool:
    """回合规则单实现：轮到友方的新回合（turn 递增 + 当前玩家是友方）。"""
    return current_player_id == friendly_player_id and turn > last_turn


@dataclass
class TurnTrigger:
    """检测回合变化并触发建议生成。

    用法：每次解析完一批新日志行后，调 check_and_trigger(result, ...)，
    若检测到"轮到友方的新回合"，则生成建议并发布。

    last_advice：上一回合的建议，LLM 全部失败时作为降级建议回显
    （spec：超时降级为上一回合建议）。
    """

    friendly_player_id: int
    last_triggered_turn: int = 0
    last_advice: Advice | None = None

    def detect_new_friendly_turn(self, snapshot: GameSnapshot) -> int | None:
        """若 snapshot 是轮到友方的新回合（turn > 上次触发的），返回 turn 号；否则 None。"""
        if _is_new_friendly_turn(
            snapshot.turn, snapshot.current_player_id, self.friendly_player_id, self.last_triggered_turn
        ):
            return snapshot.turn
        return None

    def check_and_trigger(
        self,
        game,
        db: CardDatabase | None,
        client: LLMClient,
        publish_dir: Path,
    ) -> Advice | None:
        """检查并可能触发：序列化 → 检测新回合 → 生成建议 → 发布。

        同步阻塞实现（兼容既有调用与 manual_trigger）。

        Returns: 若触发了建议返回 Advice，否则 None。
        """
        snapshot = serialize_game(game, self.friendly_player_id, db)
        new_turn = self.detect_new_friendly_turn(snapshot)
        if new_turn is None:
            return None

        self.last_triggered_turn = new_turn
        advice = self.generate_and_publish(
            snapshot, new_turn, self.last_advice, client, publish_dir
        )
        return advice

    def generate_and_publish(
        self,
        snapshot: GameSnapshot,
        turn: int,
        fallback: Advice | None,
        client: LLMClient,
        publish_dir: Path,
    ) -> Advice:
        """生成建议并发布（含 LLM 调用 + 更新 last_advice）。

        从 check_and_trigger 拆出的"慢路径"后半段，供 AdviceDispatcher
        的 worker 线程调用：调用方已在 log_worker 完成 turn 检测与
        last_triggered_turn 更新，此方法只负责 LLM + 发布 + 记 fallback。

        worker 线程独占调用，故 last_advice 的读写在此处无需加锁。
        """
        advice = get_advice(
            snapshot, client, self.friendly_player_id, fallback=fallback
        )
        self.last_advice = advice
        publish_advice(publish_dir, advice, turn)
        return advice

    def manual_trigger(
        self,
        game,
        db: CardDatabase | None,
        client: LLMClient,
        publish_dir: Path,
    ) -> Advice:
        """手动触发"再想想"：不强求 turn 递增，基于当前局面生成。"""
        snapshot = serialize_game(game, self.friendly_player_id, db)
        advice = get_advice(snapshot, client, self.friendly_player_id, fallback=self.last_advice)
        self.last_advice = advice
        publish_advice(publish_dir, advice, snapshot.turn)
        return advice


@dataclass
class IncrementalTurnDetector:
    """增量回合检测器（优化 2+3）。

    扫描原始日志行（正则，极快），检测 TURN/CURRENT_PLAYER 变化。
    只有检测到"轮到友方的新回合"时，才回调一次全量解析+LLM。
    避免每行都做 hslog 全量解析（全量 ~25ms → 正则 ~0.01ms/行）。

    用法：
        detector = IncrementalTurnDetector(friendly_player_id=1)
        for turn in detector.feed(new_lines):   # 本次触发的回合号列表
            lines = detector.get_trigger_window(turn)  # 截至该触发点的行流
            # 用 lines 全量解析 → 快照正好在该回合开始时刻

    CURRENT_PLAYER 解析：先由 CREATE_GAME 块的 "Player EntityID=N
    PlayerID=M" 建立 实体 id↔玩家 id 映射；再解析 CURRENT_PLAYER 行的
    Entity 令牌（名字或数字 id）→ 玩家 id。名字↔实体 id 是协议常量。
    注意只认 value=1 的置位行（value=0 是回合结束方，忽略）。

    触发窗口：触发发生在批内某一行，同一批可能已包含下一回合的行。
    按触发点截取行流，保证快照正是"该回合开始时刻"（否则下一回合的
    行会把快照推到对方回合，本回合建议被吞——真实踩坑）。
    """

    friendly_player_id: int
    _all_lines: list[str] = field(default_factory=list)
    _last_turn: int = 0
    _current_player: int | None = None
    _entity_to_player: dict[int, int] = field(default_factory=dict)
    _trigger_upto: dict[int, int] = field(default_factory=dict)  # turn → 触发行数

    def _resolve_player_id(self, token: str) -> int | None:
        """把 CURRENT_PLAYER 行的 Entity 令牌解析成玩家 id。"""
        if token.isdigit():
            eid = int(token)
        else:
            eid = _NAME_TO_ENTITY_ID.get(token)
            if eid is None:
                return None
        # 映射优先（来自本局 CREATE_GAME）；协议兜底：实体 2=玩家1、实体 3=玩家2
        return self._entity_to_player.get(eid, eid - 1)

    def feed(self, lines: list[str]) -> list[int]:
        """喂入新行，返回本次触发"轮到友方的新回合"的回合号列表。

        内部累积所有行。每个触发点都可用 get_trigger_window(turn)
        取截至该触发点的行流做全量解析。未触发返回空列表。
        """
        triggered: list[int] = []
        for line in lines:
            self._all_lines.append(line)
            if "CREATE_GAME" in line:
                # 新对局：清空实体映射（全量 reset 由调用方负责）
                self._entity_to_player.clear()
            elif "Player EntityID=" in line:
                m = _PLAYER_ENTITY_RE.search(line)
                if m:
                    self._entity_to_player[int(m.group(1))] = int(m.group(2))
            elif "tag=TURN" in line:
                m = _TURN_RE.search(line)
                if m:
                    turn = int(m.group(1))
                    if _is_new_friendly_turn(turn, self._current_player, self.friendly_player_id, self._last_turn):
                        self._last_turn = turn
                        self._trigger_upto[turn] = len(self._all_lines)
                        triggered.append(turn)
                    elif turn > self._last_turn:
                        self._last_turn = turn
            elif "tag=CURRENT_PLAYER" in line:
                m = _CURRENT_PLAYER_RE.search(line)
                if m:
                    token, flag = m.group(1), m.group(2)
                    if flag == "1":  # 只认"轮到谁"的置位，忽略置 0 行
                        pid = self._resolve_player_id(token)
                        if pid is not None:
                            self._current_player = pid
        return triggered

    def get_trigger_window(self, turn: int) -> list[str]:
        """返回截至指定触发回合（含其 TURN 行）的行流，用于全量解析。

        快照正好落在该回合开始时刻；同批内后续回合的行不会污染它。
        """
        upto = self._trigger_upto.get(turn, len(self._all_lines))
        return self._all_lines[:upto]

    def get_all_lines(self) -> list[str]:
        """返回累积的全部日志行（用于全量解析）。"""
        return self._all_lines

    def reset(self) -> None:
        """新对局时重置（CREATE_GAME 后调用）。"""
        self._all_lines.clear()
        self._last_turn = 0
        self._current_player = None
        self._entity_to_player.clear()
        self._trigger_upto.clear()


def publish_advice(publish_dir: Path, advice: Advice, turn: int) -> Path:
    """原子写 advice.json 到 publish_dir。

    返回写入的文件路径。读者通过监听该文件刷新 UI。
    """
    publish_dir.mkdir(parents=True, exist_ok=True)
    target = publish_dir / ADVICE_FILENAME
    payload = {
        "turn": turn,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "advice": advice.to_dict(),
    }
    # 原子写：临时文件 + os.replace
    fd, tmp_path = tempfile.mkstemp(
        dir=str(publish_dir), prefix=".advice_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target)
    except Exception:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return target


def publish_game_state(publish_dir: Path, snapshot: GameSnapshot, friendly_player_id: int) -> Path:
    """原子写 game_state.json：实时对局快照（盒子/记牌器数据源）。

    与 advice.json 同一契约精神：语言无关、文件式、原子写（tmp +
    os.replace），三期 C# WPF 可零成本复用。快照已经过 serialize_game
    的 D9 过滤（对手手牌只有数量），UI 直接消费即可，无需再过滤。
    """
    publish_dir.mkdir(parents=True, exist_ok=True)
    target = publish_dir / GAME_STATE_FILENAME
    payload = {
        "turn": snapshot.turn,
        "current_player_id": snapshot.current_player_id,
        "friendly_player_id": friendly_player_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "players": {pid: pv.to_dict() for pid, pv in snapshot.players.items()},
    }
    fd, tmp_path = tempfile.mkstemp(
        dir=str(publish_dir), prefix=".state_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return target
