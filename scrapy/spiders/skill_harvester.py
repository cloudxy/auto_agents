"""技能市场采集爬虫（方案 A · A-P5-1）

采集公开 skill 清单源，产出候选条目（source="marketplace" 直落
spider_results.source，候选 Tab 以此过滤）：
- GitHub contents API（api.github.com/repos/<o>/<r>/contents/<path>?ref=）：
  目录条目 = 候选（url=html_url，转正时正好是 import-url 的 GitHub 子目录形态）
- raw README（awesome 清单）：markdown 行 `- [title](github-url) — 描述`
转正走人工闸门（admin 候选 Tab → import_url 正式管线），采集不直接落
skills-library。反爬（延迟/UA）沿 settings 与基类站点配置。
"""
import re

from items import BaseItem
from platform_core.logger import get_logger
from spiders.base import TaskAwareRedisSpider

logger = get_logger("spider")

_AWESOME_LINE = re.compile(
    r"^-\s*\[(?P<title>[^\]]+)\]\((?P<url>https://github\.com/[^\s)]+)\)\s*[—\-–]+\s*(?P<desc>.+)$"
)


class SkillHarvesterSpider(TaskAwareRedisSpider):
    """技能市场采集（候选 → 人工审核 → import-url 转正）"""

    name = "skill_harvester"
    redis_key = "skill_harvester:start_urls"
    allowed_domains = ["api.github.com", "raw.githubusercontent.com", "github.com"]

    def parse(self, response):
        logger.info(f"市场采集解析: {response.url}")
        content_type = response.headers.get("Content-Type", b"").decode()
        if "application/json" in content_type:
            yield from self._parse_github_contents(response)
        else:
            yield from self._parse_awesome_readme(response)

    def _parse_github_contents(self, response):
        """GitHub contents API：目录条目即候选（file 条目跳过）"""
        import json
        from urllib.parse import urlparse

        path = urlparse(response.url).path  # /repos/<o>/<r>/contents/<sub>?...
        parts = path.split("/")
        repo = "/".join(parts[2:4]) if len(parts) >= 4 else ""
        try:
            entries = json.loads(response.text)
        except ValueError:
            logger.warning(f"contents API 响应非 JSON: {response.url}")
            return
        if not isinstance(entries, list):
            logger.warning(f"contents API 返回非数组（可能是文件详情/错误）: {response.url}")
            return
        for entry in entries:
            if entry.get("type") != "dir":
                continue
            item = BaseItem()
            item["url"] = entry.get("html_url") or ""
            item["title"] = entry.get("name") or ""
            item["content"] = ""
            item["source"] = "marketplace"
            item["extra"] = {"repo": repo, "kind": "github_dir"}
            if item["url"] and item["title"]:
                yield item

    def _parse_awesome_readme(self, response):
        """awesome 清单 README：markdown 链接行 = 候选（仅 github 链接）"""
        for line in response.text.splitlines():
            match = _AWESOME_LINE.match(line.strip())
            if not match:
                continue
            repo = "/".join(match.group("url").split("/")[3:5])
            item = BaseItem()
            item["url"] = match.group("url")
            item["title"] = match.group("title").strip()
            item["content"] = match.group("desc").strip()
            item["source"] = "marketplace"
            item["extra"] = {"repo": repo, "kind": "awesome_link"}
            yield item
