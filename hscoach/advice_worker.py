"""LLM 建议异步调度器（latest-wins）。

把"调 LLM → 发布 advice.json"这条慢路径从日志读取线程剥离，避免
LLM 慢（超时 120s）反噬日志读取与记牌器快照（game_state.json）发布。

设计：单消费 worker 线程 + 单槽 pending。
- submit(job)：生产端（log_worker / 手动触发）调用，O(1) 非阻塞。
  无条件覆盖 pending 槽——新任务到达时丢弃尚未启动的旧任务
  （latest-wins：避免堆积过时请求，LLM 配额友好）。
- run_loop(handler, stop_event)：消费端线程入口。idle 时阻塞等待
  （低开销轮询），有 pending 则取出处理。

并发契约：
- 同一时刻最多一个 handler 在跑（单 worker）。
- 正在跑的 job 不被打断；跑完才看 pending 槽。
- pending 槽最多 1 个：连续 submit(a, b, c) 且 handler 一直忙 → 只保留 c。
- 极端慢 LLM 下，UI 至少每 120s（一次 LLM 上限）拿到一次 advice 更新，
  记牌器通道始终实时（它在 log_worker 里，不经此调度器）。

worker 处理的 job.snapshot 是不可变快照（serialize_game 产物），
跨线程共享无竞争——序列化在 submit 前完成。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

# 仅类型注解用：避免运行时拉进 coach→state→hearthstone 的 import 链，
# 使本模块（纯并发组件）可独立测试，与 test_single_instance 同级。
if TYPE_CHECKING:
    from hscoach.coach import Advice
    from hscoach.state import GameSnapshot

logger = logging.getLogger(__name__)

# idle 轮询周期：submit 会主动唤醒（_pending_event.set），此周期仅作
# stop_event 兜底检查，避免 stop 时漏唤醒。取 0.2s 平衡响应与开销。
_IDLE_POLL_SEC = 0.2


class AdviceHandler(Protocol):
    """worker 消费 job 时调用的处理函数协议。"""

    def __call__(self, job: "AdviceJob") -> None: ...


@dataclass
class AdviceJob:
    """一个待处理的建议请求。

    snapshot/turn/fallback 在 submit 时确定（消费时不再变化），可安全
    跨线程读取。run_loop 的 handler 负责：调 LLM → 发布 → 更新
    trigger.last_advice（在 handler 内部完成，worker 不触碰 trigger）。
    """

    snapshot: GameSnapshot
    turn: int
    fallback: Advice | None


class AdviceDispatcher:
    """latest-wins 单消费调度器。

    线程安全：submit 可被多个生产者（log_worker、手动触发线程）并发调用。
    run_loop 只应在**单个**线程里调用。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: AdviceJob | None = None
        self._has_pending = threading.Event()  # 有 pending 时 set，唤醒 worker
        self._busy = False  # handler 正在跑（仅 worker 线程写）
        self._processed = 0  # 已处理 job 数（仅 worker 线程写）

    def submit(self, job: AdviceJob) -> None:
        """提交一个建议请求。非阻塞，覆盖未启动的旧 pending。

        若 worker 正忙，此 job 进 pending 槽排队；若 pending 已有 job，
        该旧 job 被丢弃（latest-wins：过时局面不浪费 LLM 配额）。
        """
        with self._lock:
            self._pending = job
        self._has_pending.set()  # 唤醒 idle 中的 worker

    def is_idle(self) -> bool:
        """worker 是否完全空闲（无在跑 job 且无 pending）。

        供 UI / 日志观测。注意：返回 False 不代表 handler 正在跑，
        也可能只是 pending 槽非空；二者合并为"有活干"。
        """
        with self._lock:
            pending = self._pending is not None
        return not self._busy and not pending

    def run_loop(
        self,
        handler: AdviceHandler,
        stop_event: threading.Event,
    ) -> None:
        """worker 线程入口：循环取 pending → 调 handler。

        阻塞退出条件：仅 stop_event.is_set()。退出前会尽量处理已 submit
        的 pending（最后一次），除非 stop 时 handler 尚未启动。
        """
        logger.info("建议调度器 worker 启动（latest-wins）")
        while not stop_event.is_set():
            job = self._take_pending()
            if job is None:
                # idle：等 pending 到达或 stop。_has_pending 会被 submit 置位。
                self._has_pending.wait(timeout=_IDLE_POLL_SEC)
                # 清掉可能的陈旧 set（take 前重置，避免忙循环）
                self._has_pending.clear()
                continue

            self._busy = True
            try:
                handler(job)
            except Exception:
                # handler 内部应自行处理异常（发布失败非致命）；
                # 此处兜底防 worker 挂掉。
                logger.exception("建议 handler 抛异常（已吞，worker 继续）")
            finally:
                self._busy = False
                self._processed += 1

        logger.info("建议调度器 worker 退出（已处理 %d 个 job）", self._processed)

    def _take_pending(self) -> AdviceJob | None:
        """原子取出并清空 pending 槽。无 pending 返回 None。"""
        with self._lock:
            job = self._pending
            self._pending = None
        return job
