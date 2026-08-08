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


class TailTest(unittest.TestCase):
    # tail 涉及无限生成器+后台线程，在批量 discover 时会阻止进程干净退出。
    # 默认跳过；单独验证用：RUN_TAIL_TEST=1 python -m unittest tests.test_hearthstone_log_config
    # 模式：worker 线程收集够需要的行数后自行 break 并在线程内 close 生成器
    # （生成器此刻挂起在 yield 处，close 安全，不会踩"generator already
    # executing"竞态），主线程只 join 等待。

    def _run_tail_collect(self, fake_path, needed: int, timeout: float = 5.0):
        """起一个 tail 线程收集 needed 行，返回收集到的行列表（线程已退出）。"""
        import queue
        import threading

        collected: queue.Queue = queue.Queue()

        def run_tail():
            with patch("hscoach.log_config.power_log_path", side_effect=fake_path):
                gen = tail_power_log(poll_interval=0.05)
                for line in gen:
                    collected.put(line)
                    if collected.qsize() >= needed:
                        break
                gen.close()  # 线程内关闭（此时挂起在 yield 处）

        t = threading.Thread(target=run_tail, daemon=True)
        t.start()
        lines = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                lines.append(collected.get(timeout=0.2))
            except queue.Empty:
                continue
            if len(lines) >= needed:
                break
        t.join(timeout=2)
        return lines

    @unittest.skipUnless(
        os.environ.get("RUN_TAIL_TEST"),
        "tail 测试默认跳过（无限生成器需单独运行）",
    )
    def test_tail_reads_new_lines(self):
        """tail 能读到文件新增的行。"""
        tmp = Path(tempfile.mkdtemp())
        try:
            power_log = tmp / "Power.log"
            power_log.parent.mkdir(parents=True, exist_ok=True)
            lines = self._run_tail_collect(lambda: power_log, needed=1)
            self.assertEqual(lines, [])
            power_log.write_text("D 00:00:01 test line 1\n", encoding="utf-8")
            lines = self._run_tail_collect(lambda: power_log, needed=1)
            self.assertIn("test line 1", "".join(lines))
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(
        os.environ.get("RUN_TAIL_TEST"),
        "tail 测试默认跳过（无限生成器需单独运行）",
    )
    def test_tail_rotation_reopens_and_reads_from_start(self):
        """文件被重建（截断重写）后，tail 应从头读（含 CREATE_GAME）。

        回归：旧实现靠 st_ino 检测轮换（Windows 上恒为 0 失效），重建后
        用旧句柄继续读、新行静默丢失；且 reopen 后 seek(0,2) 跳过重建后
        写的内容。现在用大小倒退检测，重建后从头读。
        """
        tmp = Path(tempfile.mkdtemp())
        try:
            power_log = tmp / "Power.log"
            power_log.parent.mkdir(parents=True, exist_ok=True)
            power_log.write_text("D 00:00:01 old line\n", encoding="utf-8")
            # 第一批：旧文件从头读到 old line
            first = self._run_tail_collect(lambda: power_log, needed=1)
            self.assertIn("old line", "".join(first))
            # 模拟炉石重启重建 Power.log：截断重写（大小倒退 → 轮换）
            power_log.write_text("CREATE_GAME\nTAG_CHANGE new game\n", encoding="utf-8")
            # 重建后的行应从头部完整读到（含 CREATE_GAME）
            second = self._run_tail_collect(lambda: power_log, needed=2)
            joined = "".join(second)
            self.assertIn("CREATE_GAME", joined)
            self.assertIn("TAG_CHANGE new game", joined)
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(
        os.environ.get("RUN_TAIL_TEST"),
        "tail 测试默认跳过（无限生成器需单独运行）",
    )
    def test_tail_path_change_switches_to_new_file(self):
        """power_log_path 变化（国服每次启动新建时间戳目录）→ 切到新文件从头读。

        回归：旧实现只在生成器启动时解析一次路径，国服重启后永远监听
        旧目录、新对局日志全丢。
        """
        tmp = Path(tempfile.mkdtemp())
        try:
            file_a = tmp / "session_a" / "Power.log"
            file_b = tmp / "session_b" / "Power.log"
            file_a.parent.mkdir(parents=True, exist_ok=True)
            file_b.parent.mkdir(parents=True, exist_ok=True)
            file_a.write_text("A old line\n", encoding="utf-8")
            file_b.write_text("CREATE_GAME\nB new line\n", encoding="utf-8")

            current = {"path": file_a}
            first = self._run_tail_collect(lambda: current["path"], needed=1)
            self.assertIn("A old line", "".join(first))

            # 模拟炉石重启：出现新的时间戳目录 → 路径变化
            current["path"] = file_b
            second = self._run_tail_collect(lambda: current["path"], needed=2)
            joined = "".join(second)
            self.assertIn("CREATE_GAME", joined)
            self.assertIn("B new line", joined)
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
