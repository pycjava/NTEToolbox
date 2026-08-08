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
    @unittest.skipUnless(
        os.environ.get("RUN_TAIL_TEST"),
        "tail 测试默认跳过（无限生成器需单独运行）",
    )
    def test_tail_reads_new_lines(self):
        """tail 能读到文件新增的行。用线程+事件干净退出避免挂住测试。"""
        import queue
        import threading

        tmp = Path(tempfile.mkdtemp())
        power_log = tmp / "Power.log"
        collected: queue.Queue = queue.Queue()
        stop_event = threading.Event()
        gen_holder: list = []

        def run_tail():
            with patch("hscoach.log_config.power_log_path", return_value=power_log):
                gen = tail_power_log(poll_interval=0.1)
                gen_holder.append(gen)
                for line in gen:
                    if stop_event.is_set():
                        break
                    collected.put(line)
                    if line.strip():
                        break

        t = threading.Thread(target=run_tail, daemon=True)
        t.start()
        time.sleep(0.3)
        power_log.parent.mkdir(parents=True, exist_ok=True)
        power_log.write_text("D 00:00:01 test line 1\n", encoding="utf-8")

        try:
            line = collected.get(timeout=3)
            self.assertIn("test line 1", line)
        finally:
            stop_event.set()
            # 关闭生成器底层文件句柄（防止 ResourceWarning + 挂住）
            for g in gen_holder:
                g.close()
            t.join(timeout=2)
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
