#!/usr/bin/env python3
"""Build a public, read-only site from two allowlisted Markdown directories."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from markdown_it import MarkdownIt

CATEGORIES = (
    ("盘前策略", "premarket", "盘前策略", "盘前分析", "开盘前，把机会与风险写清楚。"),
    ("涨停分析", "review", "涨停复盘", "涨停复盘", "收盘后，回看市场主线与资金选择。"),
)
TITLE = "A股研究站"
WARNING = "本网站内容由 AI 辅助生成，仅供研究参考，不构成收益承诺。请核验报告数据与来源；股市有风险，投资需谨慎。"
SCRIPT_DIR = Path(__file__).resolve().parent


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def text_of(markup: str) -> str:
    parser = TextExtractor()
    parser.feed(markup)
    return " ".join(" ".join(parser.parts).split())


def escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_markdown(source: str) -> tuple[str, str]:
    # Reports are data, not executable templates. Raw HTML and unsafe links are not enabled.
    md = MarkdownIt("commonmark", {"html": False, "breaks": False}).enable(["table", "strikethrough"])
    tokens = md.parse(source)
    seen: dict[str, int] = {}
    outline = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            following = tokens[index + 1]
            label = text_of(md.renderer.renderInline(following.children or [], md.options, {}))
            slug = re.sub(r"[^\w\-\s\u4e00-\u9fff]", "", label.lower(), flags=re.UNICODE)
            slug = re.sub(r"\s+", "-", slug).strip("-") or "section"
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            if count:
                slug = f"{slug}-{count}"
            token.attrSet("id", slug)
            if token.tag in ("h2", "h3"):
                outline.append(f'<a class="toc-{token.tag}" href="#{quote(slug)}">{escaped(label)}</a>')
        for child in token.children or []:
            if child.type == "link_open":
                target = child.attrGet("href") or ""
                if target.startswith(("https://", "http://")):
                    child.attrSet("target", "_blank")
                    child.attrSet("rel", "noopener noreferrer")
            if child.type == "image":
                child.attrSet("loading", "lazy")
                child.attrSet("referrerpolicy", "no-referrer")
    rendered = md.renderer.render(tokens, md.options, {})
    rendered = rendered.replace("<table>", '<div class="table-scroll" tabindex="0"><table>')
    rendered = rendered.replace("</table>", "</table></div>")
    return rendered, "".join(outline)


@dataclass(frozen=True)
class Report:
    source: Path
    relative: str
    slug: str
    category: str
    title: str
    day: date
    markdown: str

    @property
    def route(self) -> str:
        return f"{self.slug}/{self.day.year}/{self.day.month:02d}/{self.day.day:02d}.html"

    @property
    def month(self) -> str:
        return f"{self.day.year}年{self.day.month}月"

    @property
    def month_route(self) -> str:
        return f"{self.slug}/{self.day.year}/{self.day.month:02d}/index.html"


def collect_reports(root: Path) -> list[Report]:
    reports = []
    for directory, slug, category, suffix, _ in CATEGORIES:
        folder = root / directory
        if not folder.exists():
            continue
        if folder.is_symlink():
            raise ValueError(f"Refusing symlink source directory: {directory}")
        for source in sorted(folder.glob("*/*.md")):
            month_match = re.fullmatch(r"(\d{4})年(\d{1,2})月", source.parent.name)
            file_match = re.fullmatch(rf"(\d{{1,2}})月(\d{{1,2}})日{suffix}\.md", source.name)
            if not month_match or not file_match:
                print(f"SKIP (not an approved report name): {source.relative_to(root)}")
                continue
            if source.is_symlink() or source.parent.is_symlink() or not source.is_file():
                raise ValueError(f"Refusing symlink/non-file report: {source}")
            year, month = map(int, month_match.groups())
            file_month, day = map(int, file_match.groups())
            if file_month != month:
                raise ValueError(f"Folder/file month mismatch: {source}")
            report_day = date(year, month, day)  # Invalid dates fail the build.
            source_text = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
            if not source_text.strip():
                raise ValueError(f"Empty report: {source}")
            reports.append(Report(source, source.relative_to(root).as_posix(), slug,
                                  category, source.stem, report_day, source_text))
    reports.sort(key=lambda report: (report.day, report.slug), reverse=True)
    if len({r.route for r in reports}) != len(reports):
        raise ValueError("Duplicate report dates within one category")
    return reports


def build(root: Path, output: Path, base: str = "/stock/") -> int:
    root, output = root.resolve(), output.resolve()
    if not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*", base):
        raise ValueError("base must be a safe absolute URL path ending in /, e.g. /stock/")
    # Only our disposable build directories may be cleaned. Never remove repository content.
    if output.name not in {"_site", "_site-preview"} or output == root or root.is_relative_to(output):
        raise ValueError("output must be a disposable _site or _site-preview directory")
    reports = collect_reports(root)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    template = (SCRIPT_DIR / "template.html").read_text(encoding="utf-8")
    generated = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M 北京时间")

    def url(route: str = "index.html") -> str:
        return base + route

    def write(route: str, data: str) -> None:
        target = output / route
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding="utf-8")

    def report_list(items: list[Report]) -> str:
        if not items:
            return '<div class="empty">暂无已发布报告。首篇 Markdown 提交并成功发布后，会显示在这里。</div>'
        return '<div class="report-list">' + "".join(
            f'<a class="report-row" href="{url(r.route)}"><time datetime="{r.day.isoformat()}">{r.day.isoformat()}</time>'
            f'<span>{escaped(r.title)}</span><span aria-hidden="true">↗</span></a>' for r in items) + "</div>"

    def sidebar(active: Report | None = None) -> str:
        sections = []
        for _, slug, category, _, _ in CATEGORIES:
            selected = [r for r in reports if r.slug == slug]
            parts = [f'<a class="side-category" href="{url(slug + "/index.html")}">{category}<span>{len(selected)}</span></a>']
            months = list(dict.fromkeys(r.month for r in selected))
            for month in months:
                members = [r for r in selected if r.month == month]
                opened = " open" if active and active.slug == slug and active.month == month else ""
                parts.append(f'<details{opened}><summary>{month}<span>{len(members)}</span></summary>')
                parts.append(f'<a class="month-link" href="{url(members[0].month_route)}">查看整月</a>')
                for r in members:
                    current = ' aria-current="page"' if active == r else ""
                    parts.append(f'<a href="{url(r.route)}"{current}>{escaped(r.title)}</a>')
                parts.append("</details>")
            if not selected:
                parts.append('<p class="side-empty">报告发布后自动归档</p>')
            sections.append("<section>" + "".join(parts) + "</section>")
        return "".join(sections)

    def page(route: str, title: str, content: str, *, active: Report | None = None, toc: str = "") -> None:
        replacements = {"TITLE": escaped(title + " · " + TITLE), "BASE": base, "CONTENT": content,
                        "SIDEBAR": sidebar(active), "TOC": toc, "GENERATED": generated,
                        "WARNING": WARNING, "PAGE_CLASS": "article-page" if active else "index-page"}
        # Single-pass substitution: report text cannot introduce another template substitution.
        result = re.sub(r"\[\[([A-Z_]+)\]\]", lambda m: replacements[m[1]], template)
        write(route, result)

    cards = []
    for _, slug, category, _, description in CATEGORIES:
        selected = [r for r in reports if r.slug == slug]
        latest = selected[0] if selected else None
        latest_label = escaped(latest.title) if latest else "等待首篇报告"
        latest_url = url(latest.route) if latest else url(slug + "/index.html")
        cards.append(f'<section class="category-card"><div class="eyebrow">{category} · {len(selected)} 篇</div>'
                     f'<h2>{description}</h2><a class="latest-link" href="{latest_url}">{latest_label} <span>→</span></a>'
                     f'<a class="muted-link" href="{url(slug + "/index.html")}">浏览全部{category} ↗</a></section>')
    latest_day = reports[0].day.isoformat() if reports else "尚无报告"
    home = ('<header class="hero"><div class="eyebrow">MARKET RESEARCH / A股研究</div>'
            '<h1>看清市场，<br>再做决定。</h1><p>盘前策略与盘后复盘，一个入口，持续归档。<br>按日期阅读，也可以搜索股票、板块和市场线索。</p>'
            f'<div class="stats"><span><strong>{len(reports)}</strong> 篇报告</span><span><strong>2</strong> 个栏目</span><span>最近报告 <strong>{latest_day}</strong></span></div></header>'
            f'<div class="category-grid">{"".join(cards)}</div><section class="latest-section"><div class="section-heading"><h2>最近发布</h2>'
            f'<a href="{url("archive.html")}">全部归档 →</a></div>{report_list(reports[:12])}</section>')
    page("index.html", "首页", home)

    for _, slug, category, _, description in CATEGORIES:
        selected = [r for r in reports if r.slug == slug]
        content = f'<header class="page-heading"><div class="eyebrow">REPORTS / {len(selected)} 篇</div><h1>{category}</h1><p>{description}</p></header>'
        months = list(dict.fromkeys(r.month for r in selected))
        for month in months:
            members = [r for r in selected if r.month == month]
            content += f'<section class="month-section"><h2><a href="{url(members[0].month_route)}">{month}</a></h2>{report_list(members)}</section>'
            page(members[0].month_route, f"{month} · {category}",
                 f'<header class="page-heading"><div class="eyebrow">{category}</div><h1>{month}</h1><p>{len(members)} 篇报告 · 日期从新到旧</p></header>' + report_list(members))
        if not selected:
            content += report_list([])
        page(slug + "/index.html", category, content)

    archive = '<header class="page-heading"><div class="eyebrow">ARCHIVE</div><h1>全部归档</h1><p>同一个交易日的盘前策略与盘后复盘，放在一起看。</p></header>'
    dates = sorted({r.day for r in reports}, reverse=True)
    if dates:
        archive += '<div class="table-scroll"><table class="archive-table"><thead><tr><th>报告日期</th><th>盘前策略</th><th>涨停复盘</th></tr></thead><tbody>'
        for day in dates:
            archive += f'<tr><td><time>{day.isoformat()}</time></td>'
            for slug in ("premarket", "review"):
                match = next((r for r in reports if r.day == day and r.slug == slug), None)
                archive += f'<td><a href="{url(match.route)}">{escaped(match.title)}</a></td>' if match else '<td class="muted">未发布</td>'
            archive += "</tr>"
        archive += "</tbody></table></div>"
    else:
        archive += report_list([])
    page("archive.html", "全部归档", archive)

    index = []
    for report in reports:
        body, toc = render_markdown(report.markdown)
        download_route = f"markdown/{report.slug}/{report.day.isoformat()}.md"
        write(download_route, report.markdown)
        # The source remains unchanged, including all data tables, source links and warnings.
        content = (f'<nav class="breadcrumbs" aria-label="面包屑"><a href="{url(report.slug + "/index.html")}">{report.category}</a><span>/</span>'
                   f'<a href="{url(report.month_route)}">{report.month}</a></nav>'
                   f'<header class="report-heading"><div class="eyebrow">{report.category} / {report.day.isoformat()}</div><h1>{escaped(report.title)}</h1>'
                   f'<div class="article-tools"><a href="{url(download_route)}" download>下载 Markdown ↗</a><button type="button" id="print-report">打印 / 保存 PDF</button></div></header>'
                   f'<p class="research-notice">{WARNING}</p><article class="markdown-body">{body}</article>')
        same_day = next((r for r in reports if r.day == report.day and r.slug != report.slug), None)
        if same_day:
            content += f'<aside class="related"><span>同日关联报告</span><a href="{url(same_day.route)}">{escaped(same_day.title)} →</a></aside>'
        page(report.route, report.title, content, active=report, toc=toc)
        index.append({"title": report.title, "date": report.day.isoformat(), "category": report.category,
                      "url": url(report.route), "text": text_of(body)})
    write("search-index.json", json.dumps(index, ensure_ascii=False, separators=(",", ":")))
    write(".nojekyll", "")
    page("404.html", "页面不存在", f'<header class="page-heading"><div class="eyebrow">404</div><h1>这篇报告还没有发布。</h1><p>请检查链接，或从归档中重新查找。</p><a class="latest-link" href="{url()}">返回首页 →</a></header>')
    manifest = {"reports": len(reports), "generated_at": generated,
                "sources": [{"path": r.relative, "sha256": hashlib.sha256(r.markdown.encode()).hexdigest(), "page": r.route} for r in reports]}
    write("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"Built {len(reports)} real reports into {output}; base={base}")
    return len(reports)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SCRIPT_DIR.parent)
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR.parent / "_site")
    parser.add_argument("--base", default="/stock/")
    args = parser.parse_args()
    build(args.root, args.output, args.base)


if __name__ == "__main__":
    main()
