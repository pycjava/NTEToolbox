"""AdviceDispatcher（latest-wins 调度器）的单元测试。

这些测试验证 LLM 调用异步化的核心并发契约：
- submit 不阻塞（即使 handler 在跑慢的 LLM）
- stop_event 优雅退出
- latest-wins：跑一个 job 期间连续到达多个新 job，只处理最新那个，
  中间的 pending 被丢弃（不堆积过时请求）

时序控制用 gate（threading.Event）精确驱动，避免 sleep 导致 flaky。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from hscoach.advice_worker import AdviceDispatcher, AdviceJob

# 注意：不 import hscoach.coach.Advice / hscoach.state.GameSnapshot——它们
# 会拉进 hearthstone.enums（hslog 依赖，测试环境未必装）。调度器是纯并发
# 组件，对 job 内容用鸭子类型（Any）即可，无需真实卡牌类型。


@dataclass
class _FakeSnapshot:
    """GameSnapshot 的最小替身（只用 turn 字段）。"""

    turn: int


@dataclass
class _FakeAdvice:
    """Advice 的最小替身（测 fallback 透传）。"""

    headline: str = ""


def _snapshot(turn: int) -> Any:
    return _FakeSnapshot(turn=turn)


def _job(turn: int, fallback: Any = None) -> AdviceJob:
    return AdviceJob(snapshot=_snapshot(turn), turn=turn, fallback=fallback)


class _GatedHandler:
    """可观测、时序可控的 handler。

    - allow_start：worker 进入 handler 后阻塞在此，测试 set 后才真正执行，
      用来精确控制"上一个 job 何时完成"。
    - started：handler 已进入（测试据此确认 worker 正在忙）。
    - processed：已完成的 job.turn 列表（锁保护）。
    """

    def __init__(self) -> None:
        self.allow_finish = threading.Event()
        self.started = threading.Event()
        self._lock = threading.Lock()
        self.processed: list[int] = []
        self.fallbacks_seen: list[Advice | None] = []

    def __call__(self, job: AdviceJob) -> None:
        self.started.set()
        # 阻塞直到测试放行，模拟慢 LLM
        if not self.allow_finish.wait(timeout=5):
            raise TimeoutError("handler 等待 allow_finish 超时（测试设置错误）")
        with self._lock:
            self.processed.append(job.turn)
            self.fallbacks_seen.append(job.fallback)

    def reset_gate(self) -> None:
        self.started.clear()
        self.allow_finish.clear()


def _start_worker(handler, stop_event):
    """启动 dispatcher worker 线程，返回 dispatcher。"""
    d = AdviceDispatcher()
    t = threading.Thread(target=d.run_loop, args=(handler, stop_event), daemon=True)
    t.start()
    return d, t


def test_submit_does_not_block_when_handler_busy():
    """submit 必须立即返回，即使 handler 正在跑慢 LLM。

    反证：同步实现里 log_worker 调 LLM 会阻塞 ~120s；异步化后 submit 是 O(1)。
    """
    stop = threading.Event()
    handler = _GatedHandler()
    d, t = _start_worker(handler, stop)

    # 第一个 job 启动 handler（阻塞在 allow_finish）
    d.submit(_job(3))
    assert handler.started.wait(timeout=2), "worker 未启动 handler"

    # handler 正忙，submit 第二个 job 必须瞬间返回
    start = time.monotonic()
    d.submit(_job(5))
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"submit 阻塞了 {elapsed:.3f}s，应非阻塞"

    # 收尾
    handler.allow_finish.set()
    stop.set()
    t.join(timeout=3)


def test_worker_idle_waits_and_exits_on_stop():
    """worker idle 时阻塞等待，stop_event 触发后优雅退出。"""
    stop = threading.Event()
    handler = _GatedHandler()
    d, t = _start_worker(handler, stop)

    # 不提交任何 job，直接 stop
    time.sleep(0.1)  # 让 worker 进入 idle wait
    stop.set()
    t.join(timeout=3)
    assert not t.is_alive(), "worker 未在 stop 后退出"
    assert handler.processed == []


def test_latest_wins_running_job_completes_then_next():
    """T3 跑时 T5 到达 → T3 完成后跑 T5（正常排队，不丢弃在跑的）。"""
    stop = threading.Event()
    handler = _GatedHandler()
    d, t = _start_worker(handler, stop)

    d.submit(_job(3))
    assert handler.started.wait(timeout=2)
    # T3 在跑，提交 T5（进 pending）
    d.submit(_job(5))

    # 放行 T3 完成
    handler.allow_finish.set()
    # T3 处理完，worker 应立刻取 T5（重新 gate）
    handler.reset_gate()
    assert handler.started.wait(timeout=2), "T3 完成后未处理 T5"

    handler.allow_finish.set()
    stop.set()
    t.join(timeout=3)
    assert handler.processed == [3, 5]


def test_latest_wins_drops_obsolete_pending():
    """跑 T5 期间 T7、T9 连到 → 最终只跑 T5 和 T9，T7 被覆盖丢弃。

    这是 latest-wins 的核心：pending 槽最多 1，新任务覆盖旧 pending。
    """
    stop = threading.Event()
    handler = _GatedHandler()
    d, t = _start_worker(handler, stop)

    d.submit(_job(5))
    assert handler.started.wait(timeout=2)  # T5 在跑

    d.submit(_job(7))  # pending = 7
    d.submit(_job(9))  # pending = 9（覆盖 7）

    handler.allow_finish.set()  # T5 完成 → worker 取 pending=9

    handler.reset_gate()
    assert handler.started.wait(timeout=2), "未处理 T9"

    handler.allow_finish.set()
    stop.set()
    t.join(timeout=3)

    # T7 必须被丢弃，T5 和 T9 都处理
    assert handler.processed == [5, 9], f"latest-wins 失败：{handler.processed}"


def test_processed_turns_monotonic():
    """被采纳的 job turn 单调递增（连续提交不会乱序）。"""
    stop = threading.Event()
    handler = _GatedHandler()
    d, t = _start_worker(handler, stop)

    # 快速连发：fast handler（不等 gate），全应被处理且单调
    handler.allow_finish.set()  # 全程放行，handler 不阻塞
    for turn in (1, 2, 3):
        d.submit(_job(turn))
        time.sleep(0.05)  # 让 worker 有机会消费

    stop.set()
    t.join(timeout=3)
    assert handler.processed == sorted(handler.processed), "turn 非单调"


def test_fallback_passed_through_to_handler():
    """submit 时携带的 fallback（上一回合 advice）正确传到 handler。"""
    stop = threading.Event()
    handler = _GatedHandler()
    handler.allow_finish.set()
    d, t = _start_worker(handler, stop)

    fb = _FakeAdvice(headline="上一回合建议")
    d.submit(_job(3, fallback=fb))

    # 等 handler 处理完
    deadline = time.monotonic() + 2
    while not handler.processed and time.monotonic() < deadline:
        time.sleep(0.02)

    stop.set()
    t.join(timeout=3)
    assert handler.fallbacks_seen == [fb]


def test_dispatcher_exposes_busy_state():
    """dispatcher 能查询是否忙（供 UI/日志观测，非核心契约但便于调试）。"""
    stop = threading.Event()
    handler = _GatedHandler()
    d, t = _start_worker(handler, stop)

    assert d.is_idle() is True
    d.submit(_job(3))
    assert handler.started.wait(timeout=2)
    assert d.is_idle() is False  # handler 正在跑

    handler.allow_finish.set()
    # 处理完后回到 idle（无 pending）
    deadline = time.monotonic() + 2
    while not d.is_idle() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert d.is_idle() is True

    stop.set()
    t.join(timeout=3)
