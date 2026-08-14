"""hscoachd 打包脚本依赖预检测试。

回归（用户实测"启动教练后没有最新建议"）：打包机器没装 hearthstone extra
（httpx/hslog），PyInstaller 静态分析静默跳过缺失模块，构建"成功"但产物
启动即崩 ModuleNotFoundError: No module named 'httpx'；且客户端把
stdout/stderr 置 null，用户看不到任何原因。构建前必须 fail fast。
"""

import importlib.util
import unittest
from unittest.mock import patch

from tools.build_hscoachd import verify_runtime_dependencies

_REAL_FIND_SPEC = importlib.util.find_spec


def _find_spec_missing(*missing_names: str):
    def fake_find_spec(name, *args, **kwargs):
        if name in missing_names:
            return None
        return _REAL_FIND_SPEC(name, *args, **kwargs)

    return fake_find_spec


class VerifyRuntimeDependenciesTest(unittest.TestCase):
    def test_missing_module_raises_actionable_error(self):
        """缺 httpx → 构建中止，错误信息指向 hearthstone extra 安装命令。"""
        with patch("importlib.util.find_spec", side_effect=_find_spec_missing("httpx")):
            with self.assertRaises(SystemExit) as ctx:
                verify_runtime_dependencies()
        msg = str(ctx.exception)
        self.assertIn("httpx", msg)
        self.assertIn("hearthstone", msg)  # 提示安装 .[hearthstone] extra

    def test_all_present_passes(self):
        """全部依赖可导入时不抛异常。"""
        with patch("importlib.util.find_spec", return_value=object()):
            verify_runtime_dependencies()  # 不抛即通过

    def test_missing_any_single_module_fails(self):
        """hslog 缺失同样 fail fast（不只盯 httpx）。"""
        with patch("importlib.util.find_spec", side_effect=_find_spec_missing("hslog")):
            with self.assertRaises(SystemExit) as ctx:
                verify_runtime_dependencies()
        self.assertIn("hslog", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
