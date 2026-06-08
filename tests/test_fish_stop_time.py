import datetime
import importlib
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
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
        "agent.fish",
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
        pass

    class OCRResult:
        pass

    custom_recognition_mod.CustomRecognition = CustomRecognition
    custom_recognition_mod.RectType = list[int]
    agent_server_mod.AgentServer = AgentServer
    custom_action_mod.CustomAction = CustomAction
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


class DummyNode:
    def __init__(self, attach):
        self.attach = attach


class DummyContext:
    def __init__(self, attach):
        self.attach = attach

    def get_node_object(self, _node_name):
        return DummyNode(self.attach)


class DummyRunArg:
    node_name = "钓鱼"


class DummyTasker:
    def __init__(self):
        self.stopping = False
        self.controller = object()


class DummyRunContext:
    def __init__(self, attach):
        self.attach = attach
        self.tasker = DummyTasker()

    def get_node_object(self, _node_name):
        return DummyNode(self.attach)


def _base_attach(**overrides):
    attach = {
        "终止时间开关": True,
        "终止时长": 120,
        "溜鱼_midpoint_pix_range": 5,
        "溜鱼_midpoint_sleep_time": 5,
        "卖鱼买换饵开关": False,
        "买饵次数": 4,
        "S级鱼截图": False,
        "金色鱼截图": False,
        "鱼截图冷却时间": 5,
    }
    attach.update(overrides)
    return attach


class FishStopTimeTest(unittest.TestCase):
    def test_get_option_builds_stop_time_from_duration(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")
            real_datetime = datetime.datetime
            now = real_datetime(2026, 6, 2, 12, 0, 0).astimezone()

            with patch.object(fish.datetime, "datetime") as datetime_cls:
                datetime_cls.side_effect = real_datetime
                datetime_cls.now.return_value = now

                option = fish.get_option(
                    DummyContext(_base_attach(终止时长=120)),
                    DummyRunArg(),
                )

            expected = now + datetime.timedelta(minutes=120)
            self.assertEqual(option.终止时间, expected)

    def test_get_option_leaves_stop_time_disabled_by_default(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")

            option = fish.get_option(
                DummyContext(_base_attach(终止时间开关=False)),
                DummyRunArg(),
            )

            self.assertIsNone(option.终止时间)

    def test_get_option_reads_fish_screenshot_settings(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")

            option = fish.get_option(
                DummyContext(
                    _base_attach(
                        S级鱼截图=True,
                        金色鱼截图=True,
                        鱼截图冷却时间=7,
                    )
                ),
                DummyRunArg(),
            )

            self.assertTrue(option.S级鱼截图)
            self.assertTrue(option.金色鱼截图)
            self.assertFalse(hasattr(option, "S级鱼截图保存目录"))
            self.assertEqual(option.鱼截图冷却时间, 7)

    def test_fishing_saves_fish_screenshot_before_closing_catch_dialog(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")
            fish_action = fish.Fish()
            context = DummyRunContext(_base_attach(S级鱼截图=True))

            with (
                patch.object(fish, "get_img", return_value=object()),
                patch.object(fish, "reco_上鱼", return_value=False),
                patch.object(fish, "reco_获鱼", return_value=True),
                patch.object(fish, "reco_满舱_or_无饵", return_value=None),
                patch.object(fish, "reco_钓鱼按钮", return_value=False),
                patch.object(fish.rt_asst, "try_save_fish_screenshot", return_value=True) as try_save,
                patch.object(fish.time, "sleep", return_value=None),
            ):
                context.tasker.controller = type(
                    "Controller",
                    (),
                    {
                        "post_click_key": lambda self, _key: (
                            setattr(context.tasker, "stopping", True)
                            or type("Job", (), {"wait": lambda self: None})()
                        )
                    },
                )()
                fish_action.run(context, DummyRunArg())

            try_save.assert_called_once()

    def test_parse_stop_time_raises_on_missing_终止时长(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")
            attach = _base_attach()
            del attach["终止时长"]
            with self.assertRaises(ValueError) as ctx:
                fish.parse_stop_time(attach)
            self.assertIn("终止时长", str(ctx.exception))

    def test_parse_stop_time_raises_on_zero_终止时长(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")
            with self.assertRaises(ValueError) as ctx:
                fish.parse_stop_time(_base_attach(终止时长=0))
            self.assertIn("终止时长", str(ctx.exception))

    def test_parse_stop_time_raises_on_non_int_终止时长(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")
            with self.assertRaises(TypeError):
                fish.parse_stop_time(_base_attach(终止时长="abc"))

    def test_parse_stop_time_raises_on_bool_终止时长(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")
            with self.assertRaises(TypeError):
                fish.parse_stop_time(_base_attach(终止时长=True))


if __name__ == "__main__":
    unittest.main()
