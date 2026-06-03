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


class FishStopTimeTest(unittest.TestCase):
    def test_get_option_builds_stop_time_from_dropdown_parts(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")
            real_datetime = datetime.datetime
            now = real_datetime(2026, 6, 2, 12, 0, 0).astimezone()

            with patch.object(fish.datetime, "datetime") as datetime_cls:
                datetime_cls.side_effect = real_datetime
                datetime_cls.fromisoformat = real_datetime.fromisoformat
                datetime_cls.combine = real_datetime.combine
                datetime_cls.now.return_value = now

                option = fish.get_option(
                    DummyContext(
                        {
                            "终止时间开关": True,
                            "终止年": 2026,
                            "终止月": 6,
                            "终止日": 2,
                            "终止时": 23,
                            "终止分": 30,
                            "溜鱼_midpoint_pix_range": 5,
                            "溜鱼_midpoint_sleep_time": 5,
                            "卖鱼买换饵开关": False,
                            "买饵次数": 4,
                        }
                    ),
                    DummyRunArg(),
                )

            self.assertEqual(option.终止时间.year, 2026)
            self.assertEqual(option.终止时间.month, 6)
            self.assertEqual(option.终止时间.day, 2)
            self.assertEqual(option.终止时间.hour, 23)
            self.assertEqual(option.终止时间.minute, 30)
            self.assertEqual(option.终止时间.second, 0)

    def test_get_option_leaves_stop_time_disabled_by_default(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")

            option = fish.get_option(
                DummyContext(
                    {
                        "终止时间开关": False,
                        "溜鱼_midpoint_pix_range": 5,
                        "溜鱼_midpoint_sleep_time": 5,
                        "卖鱼买换饵开关": False,
                        "买饵次数": 4,
                    }
                ),
                DummyRunArg(),
            )

            self.assertIsNone(option.终止时间)

    def test_get_option_moves_past_dropdown_date_to_next_future_day(self):
        with stub_maa_modules():
            fish = importlib.import_module("agent.fish")
            real_datetime = datetime.datetime
            now = real_datetime(2026, 6, 5, 12, 0, 0).astimezone()

            with patch.object(fish.datetime, "datetime") as datetime_cls:
                datetime_cls.side_effect = real_datetime
                datetime_cls.fromisoformat = real_datetime.fromisoformat
                datetime_cls.combine = real_datetime.combine
                datetime_cls.now.return_value = now

                option = fish.get_option(
                    DummyContext(
                        {
                            "终止时间开关": True,
                            "终止年": 2026,
                            "终止月": 6,
                            "终止日": 2,
                            "终止时": 23,
                            "终止分": 30,
                            "终止秒": 5,
                            "溜鱼_midpoint_pix_range": 5,
                            "溜鱼_midpoint_sleep_time": 5,
                            "卖鱼买换饵开关": False,
                            "买饵次数": 4,
                        }
                    ),
                    DummyRunArg(),
                )

            self.assertEqual(option.终止时间.year, 2026)
            self.assertEqual(option.终止时间.month, 6)
            self.assertEqual(option.终止时间.day, 5)
            self.assertEqual(option.终止时间.hour, 23)


if __name__ == "__main__":
    unittest.main()
