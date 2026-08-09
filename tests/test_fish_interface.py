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
        self.assertEqual(options["钓鱼终止时长"]["type"], "select")

        yes_case = next(
            case
            for case in options["钓鱼终止时间开关"]["cases"]
            if case["name"] == "Yes"
        )
        self.assertEqual(yes_case["option"], ["钓鱼终止时长"])

        # Verify old dropdowns were removed
        for old_name in ("钓鱼终止年", "钓鱼终止月", "钓鱼终止日", "钓鱼终止时", "钓鱼终止分", "钓鱼终止秒"):
            self.assertNotIn(old_name, options)
        self.assertNotIn("钓鱼通用设置", options)

    def test_fish_screenshot_options_belong_to_fishing_task(self):
        interface = load_interface()
        fish_task = next(task for task in interface["task"] if task["name"] == "钓鱼")
        assist_task = next(task for task in interface["task"] if task["name"] == "实时辅助")
        options = interface["option"]

        self.assertIn("钓鱼_S级鱼截图", fish_task["option"])
        self.assertIn("钓鱼_金色鱼截图", fish_task["option"])
        self.assertIn("钓鱼_鱼截图_设置", fish_task["option"])
        self.assertNotIn("实时辅助_S级鱼截图", fish_task["option"])
        self.assertNotIn("实时辅助_S级鱼截图_设置", fish_task["option"])
        self.assertNotIn("钓鱼_S级鱼截图", assist_task["option"])
        self.assertNotIn("钓鱼_金色鱼截图", assist_task["option"])
        self.assertNotIn("钓鱼_鱼截图_设置", assist_task["option"])
        self.assertNotIn("实时辅助_S级鱼截图", assist_task["option"])
        self.assertNotIn("实时辅助_S级鱼截图_设置", assist_task["option"])

        self.assertIn("钓鱼_S级鱼截图", options)
        self.assertIn("钓鱼_金色鱼截图", options)
        self.assertIn("钓鱼_鱼截图_设置", options)
        self.assertNotIn("实时辅助_S级鱼截图", options)
        self.assertNotIn("实时辅助_S级鱼截图_设置", options)
        self.assertEqual(
            [
                input_definition["name"]
                for input_definition in options["钓鱼_鱼截图_设置"]["inputs"]
            ],
            ["鱼截图冷却时间"],
        )
        self.assertNotIn(
            "S级鱼截图保存目录",
            options["钓鱼_鱼截图_设置"]["pipeline_override"]["钓鱼"]["attach"],
        )

        s_rank_yes_case = next(
            case
            for case in options["钓鱼_S级鱼截图"]["cases"]
            if case["name"] == "Yes"
        )
        self.assertEqual(
            s_rank_yes_case["pipeline_override"]["钓鱼"]["attach"]["S级鱼截图"],
            True,
        )
        golden_yes_case = next(
            case
            for case in options["钓鱼_金色鱼截图"]["cases"]
            if case["name"] == "Yes"
        )
        self.assertEqual(
            golden_yes_case["pipeline_override"]["钓鱼"]["attach"]["金色鱼截图"],
            True,
        )


if __name__ == "__main__":
    unittest.main()
