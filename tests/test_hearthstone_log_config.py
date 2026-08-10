"""T1(02) 日志自动开启 + tail 测试。

验证（全在临时目录，绝不碰真实炉石配置）：
- log.config 不存在时创建
- 已存在且正确时不重复修改
- 已存在但内容不符时备份后更新
- 一键回滚能恢复
- tail 能读新增行
"""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from hscoach.log_config import (
    BACKUP_SUFFIX,
    LOG_CONFIG_CONTENT,
    ensure_log_config,
    hearthstone_data_dir,
    log_config_path,
    power_log_path,
    restore_log_config,
    tail_power_log,
)


class LogConfigTest(unittest.TestCase):
    """用临时目录模拟炉石数据目录，patch 路径函数。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fake_data_dir = Path(self.tmp) / "Hearthstone"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch_paths(self):
        return (
            patch("hscoach.log_config.hearthstone_data_dir", return_value=self.fake_data_dir),
            patch("hscoach.log_config.log_config_path", return_value=self.fake_data_dir / "log.config"),
            patch("hscoach.log_config.power_log_path", return_value=self.fake_data_dir / "Logs" / "Power.log"),
        )

    def test_creates_log_config_when_missing(self):
        with (
            patch("hscoach.log_config.hearthstone_data_dir", return_value=self.fake_data_dir),
            patch("hscoach.log_config.log_config_path", return_value=self.fake_data_dir / "log.config"),
        ):
            status = ensure_log_config()
            self.assertEqual(status.action, "created")
            cfg = self.fake_data_dir / "log.config"
            self.assertTrue(cfg.exists())
            content = cfg.read_text(encoding="utf-8")
            self.assertIn("[Power]", content)
            self.assertIn("FilePrinting=true", content)
            self.assertIn("LogLevel=1", content)

    def test_already_ok_does_not_modify(self):
        cfg = self.fake_data_dir / "log.config"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(LOG_CONFIG_CONTENT, encoding="utf-8")
        mtime_before = cfg.stat().st_mtime

        with (
            patch("hscoach.log_config.hearthstone_data_dir", return_value=self.fake_data_dir),
            patch("hscoach.log_config.log_config_path", return_value=cfg),
        ):
            status = ensure_log_config()
            self.assertEqual(status.action, "already_ok")
            # 文件未被改动
            self.assertEqual(cfg.stat().st_mtime, mtime_before)

    def test_updates_with_backup_when_content_differs(self):
        cfg = self.fake_data_dir / "log.config"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        original = "[SomeOther]\nVerbosity=0\n"
        cfg.write_text(original, encoding="utf-8")

        with (
            patch("hscoach.log_config.hearthstone_data_dir", return_value=self.fake_data_dir),
            patch("hscoach.log_config.log_config_path", return_value=cfg),
        ):
            status = ensure_log_config(backup=True)
            self.assertEqual(status.action, "updated")
            self.assertIsNotNone(status.backup_path)
            # 备份存在且内容是原始的
            self.assertTrue(Path(status.backup_path).exists())
            self.assertEqual(Path(status.backup_path).read_text(encoding="utf-8"), original)
            # 当前文件已更新
            self.assertIn("[Power]", cfg.read_text(encoding="utf-8"))

    def test_restore_from_backup(self):
        cfg = self.fake_data_dir / "log.config"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        original = "[Original]\nVerbosity=0\n"
        cfg.write_text(original, encoding="utf-8")
        # 手动制造备份
        backup_path = str(cfg) + BACKUP_SUFFIX
        Path(backup_path).write_text(original, encoding="utf-8")
        # 当前文件被改成工具的版本
        cfg.write_text(LOG_CONFIG_CONTENT, encoding="utf-8")

        with (
            patch("hscoach.log_config.hearthstone_data_dir", return_value=self.fake_data_dir),
            patch("hscoach.log_config.log_config_path", return_value=cfg),
        ):
            status = restore_log_config()
            self.assertEqual(status.action, "restored")
            self.assertEqual(cfg.read_text(encoding="utf-8"), original)
            # 备份已被消费
            self.assertFalse(Path(backup_path).exists())

    def test_restore_deletes_tool_created_config(self):
        """没有备份时（工具自己创建的），回滚=删除。"""
        cfg = self.fake_data_dir / "log.config"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(LOG_CONFIG_CONTENT, encoding="utf-8")

        with (
            patch("hscoach.log_config.hearthstone_data_dir", return_value=self.fake_data_dir),
            patch("hscoach.log_config.log_config_path", return_value=cfg),
        ):
            status = restore_log_config()
            self.assertEqual(status.action, "restored")
            self.assertFalse(cfg.exists())


class TailHarness:
    """长命 tail 监听线程（模拟真实 hscoachd 的单一生成器）。

    操作文件后从 collected 队列取行；不手动终止（daemon 线程，
    测试进程退出时自动结束）。不用 mock patch：并发/泄漏线程的
    patch stop 会还原模块属性、踩踏其他收集（真实踩坑），
    直接注入 path_provider 最干净。
    """

    def __init__(self, path_provider, poll_interval: float = 0.05):
        import queue
        import threading

        self.collected: queue.Queue = queue.Queue()

        def run():
            gen = tail_power_log(poll_interval=poll_interval, path_provider=path_provider)
            for line in gen:
                self.collected.put(line)

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def get(self, timeout: float = 2.0) -> str | None:
        """取一行；超时返回 None。"""
        try:
            return self.collected.get(timeout=timeout)
        except Exception:
            return None


class TailTest(unittest.TestCase):
    # tail 涉及无限生成器+后台线程，在批量 discover 时会阻止进程干净退出。
    # 默认跳过；单独验证用：RUN_TAIL_TEST=1 python -m pytest tests/test_hearthstone_log_config.py
    # 模式：TailHarness 长命线程持续收集；测试操作文件后从队列取行。

    def test_existing_file_is_tailed_not_replayed(self):
        """启动时文件已存在 → 从末尾 tail，不重放历史行。

        回归（用户报告"最新建议不是实时的"）：hscoachd 在炉石已运行时
        启动（Power.log 已存在），旧实现从头读整个文件 → 历史对局的回合
        被逐个触发（每个回合串行调 LLM 3-10 秒）→ worker 深陷历史回放，
        实时行被无限期搁置，建议/快照滞后数分钟。
        """
        tmp = Path(tempfile.mkdtemp())
        try:
            power_log = tmp / "Power.log"
            power_log.parent.mkdir(parents=True, exist_ok=True)
            power_log.write_text("".join(f"history {i}\n" for i in range(500)), encoding="utf-8")

            h = TailHarness(lambda: power_log)
            time.sleep(0.3)  # 让生成器建立句柄（从末尾）
            self.assertIsNone(
                h.get(timeout=0.5), "启动时文件已存在必须从末尾 tail，不得重放历史行"
            )

            with open(power_log, "a", encoding="utf-8") as f:
                f.write("fresh line\n")
            self.assertEqual(h.get(), "fresh line\n")
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    def test_tail_reads_new_lines(self):
        """文件不存在时等待出现 → 出现后从头读（新会话完整行）。"""
        tmp = Path(tempfile.mkdtemp())
        try:
            power_log = tmp / "Power.log"
            power_log.parent.mkdir(parents=True, exist_ok=True)

            h = TailHarness(lambda: power_log)
            time.sleep(0.3)
            self.assertIsNone(h.get(timeout=0.5))

            power_log.write_text("CREATE_GAME\nD 00:00:01 test line 1\n", encoding="utf-8")
            self.assertEqual(h.get(), "CREATE_GAME\n")
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    def test_tail_rotation_then_reads_new_content(self):
        """文件被重建（截断重写）后，新会话写入的行应从头被读到。

        轮换检测（大小倒退）→ reopen + seek(0) → 新文件完整行（含
        CREATE_GAME），不依赖本次"启动不重放"修复。
        """
        tmp = Path(tempfile.mkdtemp())
        try:
            power_log = tmp / "Power.log"
            power_log.parent.mkdir(parents=True, exist_ok=True)
            power_log.write_text("D 00:00:01 old line\n" * 200, encoding="utf-8")

            h = TailHarness(lambda: power_log)
            time.sleep(0.3)
            self.assertIsNone(h.get(timeout=0.5))  # 启动不重放

            # 模拟炉石重启重建 Power.log：同路径截断重写（大小倒退 → 轮换）
            power_log.write_text("CREATE_GAME\nTAG_CHANGE new game\n", encoding="utf-8")
            first = h.get()
            self.assertEqual(first, "CREATE_GAME\n")
            self.assertEqual(h.get(), "TAG_CHANGE new game\n")
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    def test_tail_path_change_switches_to_new_file(self):
        """power_log_path 变化（国服每次启动新建时间戳目录）→ 切到新文件从头读。"""
        tmp = Path(tempfile.mkdtemp())
        try:
            file_a = tmp / "session_a" / "Power.log"
            file_b = tmp / "session_b" / "Power.log"
            file_a.parent.mkdir(parents=True, exist_ok=True)
            file_b.parent.mkdir(parents=True, exist_ok=True)
            file_a.write_text("A old line\n", encoding="utf-8")

            current = {"path": file_a}
            h = TailHarness(lambda: current["path"])
            time.sleep(0.3)
            self.assertIsNone(h.get(timeout=0.5))  # 启动不重放

            # 模拟炉石重启：出现新的时间戳目录 → 路径变化 → 新文件从头读
            file_b.write_text("CREATE_GAME\nB new line\n", encoding="utf-8")
            current["path"] = file_b
            self.assertEqual(h.get(), "CREATE_GAME\n")
            self.assertEqual(h.get(), "B new line\n")
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
