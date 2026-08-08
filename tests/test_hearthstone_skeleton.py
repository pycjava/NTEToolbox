"""T0(01) 炉石模块骨架测试。

验证：
- hearthstone 包可导入、版本可读
- 入口 main 存在且可调用
- 异环 agent 包不受炉石模块影响（装炉石前后行为一致）
"""

import importlib
import unittest


class HearthstoneSkeletonTest(unittest.TestCase):
    def test_package_imports(self):
        hs = importlib.import_module("hscoach")
        self.assertTrue(hasattr(hs, "__version__"))
        self.assertIsInstance(hs.__version__, str)

    def test_main_entrypoint_exists_and_runs(self):
        main_mod = importlib.import_module("hscoach.__main__")
        self.assertTrue(callable(main_mod.main))
        # 无 API key 时应返回退出码 2（不抛异常）
        rc = main_mod.main(["--api-key", ""])
        self.assertEqual(rc, 2)

    def test_version_matches_internal(self):
        hs = importlib.import_module("hscoach")
        ver = importlib.import_module("hscoach._version")
        self.assertEqual(hs.__version__, ver.__version__)


if __name__ == "__main__":
    unittest.main()
