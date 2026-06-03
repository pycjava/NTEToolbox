import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.validate_schema import strip_jsonc_comments


def load_interface():
    return json.loads(
        strip_jsonc_comments(
            (ROOT / "assets" / "interface.jsonc").read_text(encoding="utf-8")
        )
    )


class FishInterfaceStopTimeTest(unittest.TestCase):
    def test_fish_stop_time_uses_dropdown_options(self):
        interface = load_interface()
        fish_task = next(task for task in interface["task"] if task["name"] == "钓鱼")

        self.assertIn("钓鱼终止时间开关", fish_task["option"])
        self.assertNotIn("钓鱼通用设置", fish_task["option"])

        options = interface["option"]
        self.assertEqual(options["钓鱼终止时间开关"]["type"], "switch")
        for option_name in (
            "钓鱼终止年",
            "钓鱼终止月",
            "钓鱼终止日",
            "钓鱼终止时",
            "钓鱼终止分",
            "钓鱼终止秒",
        ):
            self.assertEqual(options[option_name]["type"], "select")

        self.assertNotIn("钓鱼通用设置", options)


if __name__ == "__main__":
    unittest.main()
