"""T3(03) 卡牌知识库测试。

验证：
- 文本清洗正确（移除 HearthstoneJSON 标记）
- 真实构建后能查到已知卡（EX1_001 等 5 张），字段正确
- 离线查询（构建后断网仍可查）
- 渲染图 URL 生成正确
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from hscoach.cards import (
    DEFAULT_LOCALE,
    CardDatabase,
    clean_text,
)


class CleanTextTest(unittest.TestCase):
    def test_strips_bold_italic_tags(self):
        self.assertEqual(clean_text("<b>战吼：</b>造成伤害"), "战吼：造成伤害")

    def test_converts_paragraph_and_bullet_markers(self):
        self.assertEqual(clean_text("第一行$第二行"), "第一行\n第二行")
        self.assertIn("•", clean_text("#项目"))

    def test_removes_anchor_and_placeholders(self):
        self.assertEqual(clean_text("[x]对 {0} 点伤害"), "对 X 点伤害")

    def test_empty_and_none(self):
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text(""), "")

    def test_compression_of_excess_newlines(self):
        cleaned = clean_text("a$\n$\n$\nb")
        self.assertNotIn("\n\n\n", cleaned)


class CardDatabaseTest(unittest.TestCase):
    """用真实 HearthstoneJSON 构建一次（验证数据源真实可用），后续断网可测。"""

    @classmethod
    def setUpClass(cls):
        # 用临时缓存目录，避免污染源码树
        cls.tmp_dir = Path(__file__).resolve().parent / "_hs_cache"
        cls.db = CardDatabase(cache_dir=cls.tmp_dir, locale=DEFAULT_LOCALE)
        cls.db.build()

    @classmethod
    def tearDownClass(cls):
        # 保留缓存供离线测试复用；如需清理可手动删 tests/_hs_cache
        pass

    def test_database_not_empty(self):
        # 全卡池应有数千张
        self.assertGreater(len(self.db), 1000)

    def test_known_card_lightwarden(self):
        """EX1_001 圣光护卫者（经典1费1/2，每当有角色被治疗+2攻击力）。"""
        card = self.db.get("EX1_001")
        self.assertIsNotNone(card)
        self.assertEqual(card.cost, 1)
        self.assertEqual(card.attack, 1)
        self.assertEqual(card.health, 2)
        self.assertEqual(card.type, "MINION")

    def test_known_card_fireball(self):
        """CS2_029 火球术（法师4费，造成6点伤害）。"""
        card = self.db.get("CS2_029")
        self.assertIsNotNone(card)
        self.assertEqual(card.name, "火球术")
        self.assertEqual(card.cost, 4)
        self.assertEqual(card.type, "SPELL")
        self.assertIn("6", card.text)  # 文本含伤害数值

    def test_text_is_cleaned(self):
        """查询出的 text 不应再含 HearthstoneJSON 标记。"""
        card = self.db.get("EX1_001")
        self.assertIsNotNone(card)
        self.assertNotIn("<b>", card.text)
        self.assertNotIn("[x]", card.text)

    def test_offline_query_after_build(self):
        """构建后断网仍可查询（模拟：patch 掉 _download，确认仍能从缓存查）。"""
        with patch.object(CardDatabase, "_download", side_effect=AssertionError("不应联网")):
            fresh = CardDatabase(cache_dir=self.tmp_dir, locale=DEFAULT_LOCALE)
            fresh.build()  # 命中缓存，不触发 _download
            self.assertIsNotNone(fresh.get("EX1_001"))

    def test_render_image_url(self):
        url = self.db.render_image_url("EX1_001")
        self.assertIn("EX1_001", url)
        self.assertIn("zhCN", url)

    def test_missing_card_returns_none(self):
        self.assertIsNone(self.db.get("NONEXISTENT_99999"))


if __name__ == "__main__":
    unittest.main()
