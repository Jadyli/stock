"""Tests use synthetic documents only; fixtures are never published to the real site."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("stock_build", Path(__file__).with_name("build.py"))
builder = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = builder
spec.loader.exec_module(builder)


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "_site"

    def tearDown(self):
        self.temp.cleanup()

    def report(self, path, text="# 测试样本（非真实报告）\n\n## 数据\n测试内容。\n"):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def test_empty_site(self):
        self.assertEqual(builder.build(self.root, self.output), 0)
        self.assertIn("暂无已发布报告", (self.output / "index.html").read_text())
        self.assertEqual(json.loads((self.output / "search-index.json").read_text()), [])
        self.assertTrue((self.output / "premarket/index.html").is_file())
        self.assertTrue((self.output / "review/index.html").is_file())

    def test_numeric_dates_and_same_day_links(self):
        for name in ["9月2日", "9月10日"]:
            self.report(f"盘前策略/2026年9月/{name}盘前分析.md")
        self.report("涨停分析/2026年9月/9月10日涨停复盘.md")
        self.report("盘前策略/2026年10月/10月1日盘前分析.md")
        self.assertEqual(builder.build(self.root, self.output), 4)
        index = json.loads((self.output / "search-index.json").read_text())
        self.assertEqual(index[0]["date"], "2026-10-01")
        self.assertEqual(index[-1]["date"], "2026-09-02")
        page = (self.output / "premarket/2026/09/10.html").read_text()
        self.assertIn("/stock/review/2026/09/10.html", page)
        self.assertTrue((self.output / "premarket/2026/10/index.html").exists())

    def test_full_table_and_unicode_search(self):
        source = "# 测试样本\n\n## 完整列表\n\n| 编号 | 名称 |\n|---|---|\n"
        source += "\n".join(f"| {i:06d} | 测试反转{i} |" for i in range(1, 101))
        self.report("涨停分析/2026年9月/9月23日涨停复盘.md", source)
        builder.build(self.root, self.output)
        page = (self.output / "review/2026/09/23.html").read_text()
        self.assertEqual(page.count("<tr>"), 101)
        self.assertIn('id="完整列表"', page)
        self.assertIn("000100", json.loads((self.output / "search-index.json").read_text())[0]["text"])
        self.assertEqual((self.output / "markdown/review/2026-09-23.md").read_text(), source)

    def test_only_allowlisted_reports_are_published(self):
        self.report("README.md", "PRIVATE_ROOT_CONTENT")
        self.report("秘密/2026年9月/9月23日盘前分析.md", "PRIVATE_OTHER_CONTENT")
        self.report("盘前策略/2026年9月/内部说明.md", "PRIVATE_NON_REPORT_CONTENT")
        self.report("盘前策略/2026年9月/9月23日盘前分析.md")
        self.assertEqual(builder.build(self.root, self.output), 1)
        files = "\n".join(p.read_text() for p in self.output.rglob("*") if p.is_file())
        self.assertNotIn("PRIVATE_", files)

    def test_raw_html_and_unsafe_links_do_not_execute(self):
        markup, _ = builder.render_markdown('<script>alert("test")</script>\n\n[x](javascript:alert(1))\n\n![x](data:image/svg+xml;base64,test)')
        self.assertNotIn("<script>", markup)
        self.assertNotIn('href="javascript:', markup)
        self.assertNotIn('src="data:image/svg', markup)
        self.assertIn("&lt;script&gt;", markup)

    def test_template_substitution_is_single_pass(self):
        self.report("盘前策略/2026年9月/9月23日盘前分析.md", "# 测试样本\n\n[[CONTENT]] [[SIDEBAR]]")
        builder.build(self.root, self.output)
        page = (self.output / "premarket/2026/09/23.html").read_text()
        self.assertIn("[[CONTENT]] [[SIDEBAR]]", page)

    def test_invalid_dates_fail(self):
        self.report("盘前策略/2026年2月/2月30日盘前分析.md")
        with self.assertRaises(ValueError):
            builder.collect_reports(self.root)

    def test_mismatched_month_fails(self):
        self.report("盘前策略/2026年9月/10月1日盘前分析.md")
        with self.assertRaises(ValueError):
            builder.collect_reports(self.root)

    def test_empty_report_fails(self):
        self.report("盘前策略/2026年9月/9月23日盘前分析.md", "  \n")
        with self.assertRaises(ValueError):
            builder.collect_reports(self.root)

    def test_duplicate_date_fails(self):
        self.report("盘前策略/2026年9月/9月2日盘前分析.md")
        self.report("盘前策略/2026年9月/09月02日盘前分析.md")
        with self.assertRaises(ValueError):
            builder.collect_reports(self.root)

    def test_symlink_fails(self):
        target = self.report("private.md", "NOT_FOR_PUBLICATION")
        link = self.root / "盘前策略/2026年9月/9月23日盘前分析.md"
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            builder.collect_reports(self.root)

    def test_output_and_base_guards(self):
        for target in (self.root, self.root / "盘前策略", self.root / ".git"):
            with self.assertRaises(ValueError):
                builder.build(self.root, target)
        with self.assertRaises(ValueError):
            builder.build(self.root, self.output, '//external.example/')


if __name__ == "__main__":
    unittest.main()
