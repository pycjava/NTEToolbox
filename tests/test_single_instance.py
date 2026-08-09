import os

from hscoach.single_instance import SingleInstanceLock, _process_alive

DEAD_PID = 999_999_999


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
    (tmp_path / "hscoachd.lock").write_text(str(DEAD_PID), encoding="utf-8")

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
    assert _process_alive(DEAD_PID) is False
    assert _process_alive(0) is False
    assert _process_alive(-1) is False
