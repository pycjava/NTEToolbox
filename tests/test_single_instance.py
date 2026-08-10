import os
from pathlib import Path

from hscoach.single_instance import SingleInstanceLock, _process_alive

# 用作"已死进程 PID"的占位值。安全依据：Windows PID 实际为 32 位，
# 但系统分配的 PID 远小于此（通常 5-6 位数）；这个值在所有支持的平台上
# 都不会被分配给真实进程。沿用既有测试语义，仅改名澄清。
VACANT_PID = 999_999_999


def test_acquire_creates_lock_file_with_own_pid(tmp_path):
    lock = SingleInstanceLock(tmp_path)
    ok, message = lock.acquire()

    assert ok is True
    assert message == ""
    lock_file = tmp_path / "hscoachd.lock"
    assert lock_file.is_file()
    assert int(lock_file.read_text(encoding="utf-8").strip()) == os.getpid()


def test_second_acquire_rejected_while_instance_alive(tmp_path):
    lock = SingleInstanceLock(tmp_path)
    ok, _ = lock.acquire()
    assert ok is True

    # 同一进程再 acquire：PID 存活 → 拒绝
    ok, message = SingleInstanceLock(tmp_path).acquire()
    assert ok is False
    assert "正在运行" in message


def test_stale_lock_is_taken_over_when_pid_dead(tmp_path):
    # 残留锁：PID 已死
    (tmp_path / "hscoachd.lock").write_text(str(VACANT_PID), encoding="utf-8")

    ok, message = SingleInstanceLock(tmp_path).acquire()
    assert ok is True
    assert message == ""
    # 接管后锁文件是自己的 PID
    assert int((tmp_path / "hscoachd.lock").read_text(encoding="utf-8").strip()) == os.getpid()


def test_corrupt_lock_file_is_taken_over(tmp_path):
    (tmp_path / "hscoachd.lock").write_text("not-a-pid", encoding="utf-8")

    ok, _ = SingleInstanceLock(tmp_path).acquire()
    assert ok is True


def test_release_removes_lock_file(tmp_path):
    lock = SingleInstanceLock(tmp_path)
    lock.acquire()
    lock.release()

    assert not (tmp_path / "hscoachd.lock").exists()


def test_process_alive_heuristics():
    assert _process_alive(os.getpid()) is True
    assert _process_alive(VACANT_PID) is False
    assert _process_alive(0) is False
    assert _process_alive(-1) is False


def test_acquire_does_not_recurse_when_unlink_fails(tmp_path, monkeypatch):
    """回归：残留锁的 unlink 失败时不得递归调用 acquire（旧实现会
    无限递归 → RecursionError）。应返回有意义的错误而非崩溃。

    构造：预置一个 PID 已死的锁文件（走 FileExistsError 分支），
    monkeypatch 让 unlink 抛 OSError → 旧实现在 except OSError: pass
    后无条件 return self.acquire() → 死循环/栈溢出。
    """
    (tmp_path / "hscoachd.lock").write_text(str(VACANT_PID), encoding="utf-8")

    # unlink 模拟失败（只读 FS / 权限不足等真实场景）
    def _raise_oserror(self, *args, **kwargs):
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(Path, "unlink", _raise_oserror)

    lock = SingleInstanceLock(tmp_path)
    # 不得抛 RecursionError，应返回 (False, 消息)
    ok, message = lock.acquire()
    assert ok is False
    assert "无法" in message or "失败" in message
