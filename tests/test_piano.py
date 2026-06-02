import importlib
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def stub_maa_modules():
    root = Path(__file__).resolve().parents[1]
    module_names = (
        "agent",
        "agent.global_val",
        "agent.log",
        "agent.pienv",
        "agent.piano",
        "agent.virtual_key",
        "maa",
        "maa.agent",
        "maa.agent.agent_server",
        "maa.custom_action",
    )
    sentinel = object()
    original_modules = {name: sys.modules.get(name, sentinel) for name in module_names}

    agent_pkg = types.ModuleType("agent")
    agent_pkg.__path__ = [str(root / "agent")]

    maa_pkg = types.ModuleType("maa")
    maa_agent_pkg = types.ModuleType("maa.agent")
    agent_server_mod = types.ModuleType("maa.agent.agent_server")
    custom_action_mod = types.ModuleType("maa.custom_action")

    class AgentServer:
        @staticmethod
        def custom_action(_name):
            return lambda cls: cls

    class CustomAction:
        class RunArg:
            pass

    agent_server_mod.AgentServer = AgentServer
    custom_action_mod.CustomAction = CustomAction

    sys.modules["agent"] = agent_pkg
    sys.modules["maa"] = maa_pkg
    sys.modules["maa.agent"] = maa_agent_pkg
    sys.modules["maa.agent.agent_server"] = agent_server_mod
    sys.modules["maa.custom_action"] = custom_action_mod

    try:
        yield
    finally:
        for name, module in original_modules.items():
            if module is sentinel:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class PianoMidiRangeTest(unittest.TestCase):
    def test_midi_range_handles_notes_without_overflow(self):
        with stub_maa_modules():
            piano = importlib.import_module("agent.piano")

            self.assertEqual(piano.get_midi_range([60, 72, 95]), (60, 95, [], []))

    def test_midi_range_reports_low_and_high_overflow_notes(self):
        with stub_maa_modules():
            piano = importlib.import_module("agent.piano")

            self.assertEqual(
                piano.get_midi_range([58, 60, 72, 96, 100]),
                (58, 100, [58], [96, 100]),
            )


if __name__ == "__main__":
    unittest.main()
