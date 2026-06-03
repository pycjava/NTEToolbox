import importlib
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


@contextmanager
def stub_maa_modules():
    root = Path(__file__).resolve().parents[1]
    module_names = (
        "agent",
        "agent.global_val",
        "agent.log",
        "agent.maafw_tools",
        "agent.pienv",
        "agent.rt_asst",
        "agent.utils",
        "agent.virtual_key",
        "maa",
        "maa.agent",
        "maa.agent.agent_server",
        "maa.custom_action",
        "maa.custom_recognition",
        "maa.define",
    )
    sentinel = object()
    original_modules = {name: sys.modules.get(name, sentinel) for name in module_names}

    agent_pkg = types.ModuleType("agent")
    agent_pkg.__path__ = [str(root / "agent")]

    maa_pkg = types.ModuleType("maa")
    maa_agent_pkg = types.ModuleType("maa.agent")
    agent_server_mod = types.ModuleType("maa.agent.agent_server")
    custom_action_mod = types.ModuleType("maa.custom_action")
    custom_recognition_mod = types.ModuleType("maa.custom_recognition")
    define_mod = types.ModuleType("maa.define")

    class AgentServer:
        @staticmethod
        def custom_action(_name):
            return lambda cls: cls

        @staticmethod
        def custom_recognition(_name):
            return lambda cls: cls

    class CustomAction:
        class RunArg:
            pass

    class CustomRecognition:
        @staticmethod
        def custom_recognition(_name):
            return lambda cls: cls

    RectType = list[int]

    class OCRResult:
        pass

    agent_server_mod.AgentServer = AgentServer
    custom_action_mod.CustomAction = CustomAction
    custom_recognition_mod.CustomRecognition = CustomRecognition
    custom_recognition_mod.RectType = RectType
    define_mod.OCRResult = OCRResult

    sys.modules["agent"] = agent_pkg
    sys.modules["maa"] = maa_pkg
    sys.modules["maa.agent"] = maa_agent_pkg
    sys.modules["maa.agent.agent_server"] = agent_server_mod
    sys.modules["maa.custom_action"] = custom_action_mod
    sys.modules["maa.custom_recognition"] = custom_recognition_mod
    sys.modules["maa.define"] = define_mod

    try:
        yield
    finally:
        for name, module in original_modules.items():
            if module is sentinel:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class DummyBox:
    x = 0
    y = 0
    w = 1
    h = 1


class DummyRecoDetail:
    box = DummyBox()


class DummyContext:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def run_recognition(self, name, img, *, pipeline_override):
        del img
        self.calls.append((name, pipeline_override))
        return DummyRecoDetail() if self.hits.get(name, False) else None


class DummyNode:
    def __init__(self, attach):
        self.attach = attach


class DummyOptionContext:
    def __init__(self, attach):
        self.attach = attach

    def get_node_object(self, _node_name):
        return DummyNode(self.attach)


class DummyRunArg:
    node_name = "实时辅助"


class RtAsstSRankScreenshotTest(unittest.TestCase):
    def test_reco_s_rank_golden_fish_requires_golden_background_and_s_icon(self):
        with stub_maa_modules():
            rt_asst = importlib.import_module("agent.rt_asst")

            self.assertTrue(
                rt_asst.reco_s_rank_golden_fish(
                    DummyContext(
                        {
                            "reco_s_rank_golden_fish_golden_bg": True,
                            "reco_s_rank_golden_fish_s_icon": True,
                        }
                    ),
                    object(),
                )
            )
            self.assertFalse(
                rt_asst.reco_s_rank_golden_fish(
                    DummyContext(
                        {
                            "reco_s_rank_golden_fish_golden_bg": True,
                            "reco_s_rank_golden_fish_s_icon": False,
                        }
                    ),
                    object(),
                )
            )
            self.assertFalse(
                rt_asst.reco_s_rank_golden_fish(
                    DummyContext(
                        {
                            "reco_s_rank_golden_fish_golden_bg": False,
                            "reco_s_rank_golden_fish_s_icon": True,
                        }
                    ),
                    object(),
                )
            )

    def test_s_rank_screenshot_saves_once_within_cooldown(self):
        with stub_maa_modules(), TemporaryDirectory() as temp_dir:
            rt_asst = importlib.import_module("agent.rt_asst")
            option = rt_asst.Rt_asst_option(
                自动拾取=True,
                永远拾取=False,
                S级鱼截图=True,
                S级鱼截图保存目录=temp_dir,
                S级鱼截图冷却时间=5,
            )
            state = rt_asst.SRankFishScreenshotState()

            with (
                patch.object(rt_asst, "reco_s_rank_golden_fish", return_value=True),
                patch.object(rt_asst, "save_img", return_value=True) as save_img,
                patch.object(rt_asst.time, "time", side_effect=[100.0, 102.0, 106.0]),
            ):
                self.assertTrue(
                    rt_asst.try_save_s_rank_fish_screenshot(
                        DummyContext({}), object(), option, state
                    )
                )
                self.assertFalse(
                    rt_asst.try_save_s_rank_fish_screenshot(
                        DummyContext({}), object(), option, state
                    )
                )
                self.assertTrue(
                    rt_asst.try_save_s_rank_fish_screenshot(
                        DummyContext({}), object(), option, state
                    )
                )

            self.assertEqual(save_img.call_count, 2)
            saved_paths = [call.args[1] for call in save_img.call_args_list]
            self.assertTrue(all(Path(path).parent == Path(temp_dir) for path in saved_paths))
            self.assertTrue(all(Path(path).suffix == ".png" for path in saved_paths))

    def test_s_rank_screenshot_does_not_require_auto_pick(self):
        with stub_maa_modules(), TemporaryDirectory() as temp_dir:
            rt_asst = importlib.import_module("agent.rt_asst")
            option = rt_asst.Rt_asst_option(
                自动拾取=False,
                永远拾取=False,
                S级鱼截图=True,
                S级鱼截图保存目录=temp_dir,
                S级鱼截图冷却时间=5,
            )

            with (
                patch.object(rt_asst, "reco_s_rank_golden_fish", return_value=True),
                patch.object(rt_asst, "save_img", return_value=True) as save_img,
                patch.object(rt_asst.time, "time", return_value=100.0),
            ):
                self.assertTrue(
                    rt_asst.try_save_s_rank_fish_screenshot(
                        DummyContext({}),
                        object(),
                        option,
                        rt_asst.SRankFishScreenshotState(),
                    )
                )

            save_img.assert_called_once()

    def test_get_option_reads_s_rank_screenshot_settings(self):
        with stub_maa_modules():
            rt_asst = importlib.import_module("agent.rt_asst")

            option = rt_asst.get_option(
                DummyOptionContext(
                    {
                        "自动拾取": True,
                        "永远拾取": False,
                        "S级鱼截图": True,
                        "S级鱼截图保存目录": "captures",
                        "S级鱼截图冷却时间": 7,
                    }
                ),
                DummyRunArg(),
            )

            self.assertTrue(option.S级鱼截图)
            self.assertEqual(option.S级鱼截图保存目录, "captures")
            self.assertEqual(option.S级鱼截图冷却时间, 7)


if __name__ == "__main__":
    unittest.main()
