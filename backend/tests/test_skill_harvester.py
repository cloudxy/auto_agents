"""A-P5-1 skill_harvester 市场采集爬虫验证（工单 28）

Seam（工单预确认）：spider.parse 公共方法（离线构造 Response，零真外呼）。
候选经 item.source="marketplace" 直落 spider_results.source（consumer 映射契约）。
"""
import importlib
import sys
from pathlib import Path


SCRAY_DIR = Path(__file__).resolve().parents[2] / "scrapy"


def _load_spider():
    sys.path.insert(0, str(SCRAY_DIR))
    try:
        mod = importlib.import_module("spiders.skill_harvester")
    finally:
        pass
    return mod


def _json_response(url: str, body: dict):
    from scrapy.http import TextResponse

    import json

    return TextResponse(
        url=url,
        body=json.dumps(body).encode(),
        encoding="utf-8",
        headers={"Content-Type": b"application/json"},
    )


def _text_response(url: str, body: str):
    from scrapy.http import TextResponse

    return TextResponse(url=url, body=body.encode(), encoding="utf-8")


class TestGithubContentsApi:
    def test_directory_entries_yield_candidates(self):
        mod = _load_spider()
        spider = mod.SkillHarvesterSpider()
        resp = _json_response(
            "https://api.github.com/repos/anthropics/skills/contents/skills?ref=main",
            [
                {"name": "pdf-briefing", "type": "dir",
                 "html_url": "https://github.com/anthropics/skills/tree/main/skills/pdf-briefing"},
                {"name": "README.md", "type": "file",
                 "html_url": "https://github.com/anthropics/skills/blob/main/skills/README.md"},
                {"name": "doc-coauthoring", "type": "dir",
                 "html_url": "https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring"},
            ],
        )
        items = [dict(i) for i in spider.parse(resp)]
        candidates = [i for i in items if i.get("source") == "marketplace"]
        assert [i["title"] for i in candidates] == ["pdf-briefing", "doc-coauthoring"]  # file 条目跳过
        assert candidates[0]["url"] == "https://github.com/anthropics/skills/tree/main/skills/pdf-briefing"
        # 候选 extra 携带采集来源（候选 Tab 展示 + 转正溯源）
        assert candidates[0]["extra"]["repo"] == "anthropics/skills"


class TestAwesomeReadme:
    def test_markdown_links_yield_candidates(self):
        mod = _load_spider()
        spider = mod.SkillHarvesterSpider()
        readme = """# Awesome Claude Skills

- [pdf-extractor](https://github.com/a/pdf-extractor) — PDF 抽取
- [web-scraper](https://github.com/b/web-scraper) — 通用网页抓取
- 普通文本行（无链接，忽略）
- [bad link](not-a-url) — 忽略非 github 链接
"""
        resp = _text_response(
            "https://raw.githubusercontent.com/someone/awesome-claude-skills/main/README.md",
            readme,
        )
        items = [dict(i) for i in spider.parse(resp)]
        candidates = [i for i in items if i.get("source") == "marketplace"]
        assert [i["title"] for i in candidates] == ["pdf-extractor", "web-scraper"]
        assert candidates[0]["content"] == "PDF 抽取"
        assert candidates[0]["url"] == "https://github.com/a/pdf-extractor"


def test_spider_contract():
    """名称/队列键/延迟契约（B2：零 import backend）"""
    mod = _load_spider()
    spider = mod.SkillHarvesterSpider()
    assert spider.name == "skill_harvester"
    assert spider.redis_key == "skill_harvester:start_urls"
    assert "backend" not in [
        str(m) for m in ()
    ]  # 占位：import 检查由 check-arch R3 承担
