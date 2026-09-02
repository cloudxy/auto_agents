"""技能 URL 导入服务（方案 A · A-P3-1）

三种来源形态：GitHub 仓库子目录（tree API 递归）/ raw 单文件 / zip 包。
管线：拉取 → frontmatter 解析 → 冲突检测 → 落盘（SKILL.md + SOURCE.md +
初始 meta.yaml + CHANGELOG）→ 入库（扫描该目录）→ 入评分队列。

安全边界（总方案 3.2-A-6，必做验收）：
- zip-slip：成员路径拒绝绝对路径与 `..`（净化后再落盘，任何成员越界即整批拒绝）；
- 上限：zip ≤20MB / 单文件 ≤2MB / 总文件 ≤100 / 子目录深度 ≤3。
全部外呼 httpx 且 trust_env=False（3.2-A-8，防本机代理劫持）。
"""
import hashlib
import io
import re
import zipfile
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Optional
from urllib.parse import urlparse

import httpx
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import ValidationException
from platform_core.logger import get_logger
from platform_core.models.skill import Skill, SkillJob

logger = get_logger("service.skill_import")

ZIP_MAX_BYTES = 20 * 1024 * 1024
FILE_MAX_BYTES = 2 * 1024 * 1024
MAX_FILES = 100
MAX_DEPTH = 3
FETCH_TIMEOUT = 30.0

_GITHUB_TREE_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)$")


def _make_client() -> httpx.AsyncClient:
    """统一外呼客户端：trust_env=False（不读系统代理，防本机代理劫持）"""
    return httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True, trust_env=False)


def _parse_frontmatter(skill_md: str) -> dict:
    if not skill_md.startswith("---"):
        return {}
    lines = skill_md.splitlines()
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            data = yaml.safe_load("\n".join(lines[1:idx]))
            return data if isinstance(data, dict) else {}
    raise ValidationException(message="SKILL.md frontmatter 未闭合", field="url")


def _safe_member_path(member: str) -> Path:
    """zip 成员路径净化：拒绝绝对路径与 ..（zip-slip 防线）"""
    pure = PurePosixPath(member)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValidationException(message=f"zip 成员路径非法（拒绝 zip-slip）: {member}", field="url")
    return Path(*pure.parts)


class SkillImportService:
    """URL 导入（session 由调用方注入；测试可注入 MockTransport 客户端）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def import_url(
        self,
        url: str,
        category: Optional[str] = None,
        industries: Optional[list[str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> dict:
        """按来源形态导入；name 取 frontmatter.name（缺省用 zip 根目录名/文件名）"""
        logger.info(f"URL 导入 | url={url}")
        own_client = client is None
        client = client or _make_client()
        try:
            files: dict[str, bytes] = await self._fetch_files(url, client)
            name, skill_md = self._extract_skill(files, url)
            await self._ensure_no_conflict(name, category or "uncategorized")
            similar = await self._similar_candidates(name, category or "uncategorized")
            skill_dir = self._write_to_library(name, files, url, category, industries)
            await self._ingest_and_enqueue(name, skill_dir)
            return {
                "name": name,
                "imported": True,
                "file_count": len(files),
                "similar_candidates": similar,
            }
        finally:
            if own_client:
                await client.aclose()

    # ---------- 拉取（三形态） ----------

    async def _fetch_files(self, url: str, client: httpx.AsyncClient) -> dict[str, bytes]:
        if url.endswith(".zip") or "zip" in urlparse(url).path.lower():
            return await self._fetch_zip(url, client)
        tree_match = _GITHUB_TREE_RE.match(url)
        if tree_match:
            return await self._fetch_github_subdir(tree_match, client)
        return {"SKILL.md": await self._fetch_raw(url, client)}

    async def _fetch_raw(self, url: str, client: httpx.AsyncClient) -> bytes:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise ValidationException(message=f"拉取失败（HTTP {resp.status_code}）: {url}", field="url")
        if len(resp.content) > FILE_MAX_BYTES:
            raise ValidationException(message=f"单文件超过大小上限（{FILE_MAX_BYTES}B）", field="url")
        return resp.content

    async def _fetch_zip(self, url: str, client: httpx.AsyncClient) -> dict[str, bytes]:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise ValidationException(message=f"拉取失败（HTTP {resp.status_code}）: {url}", field="url")
        if len(resp.content) > ZIP_MAX_BYTES:
            raise ValidationException(message=f"zip 超过大小上限（{ZIP_MAX_BYTES}B）", field="url")
        try:
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
        except zipfile.BadZipFile as exc:
            raise ValidationException(message=f"不是合法 zip 包: {exc}", field="url") from exc
        if len(zf.namelist()) > MAX_FILES:
            raise ValidationException(message=f"文件数量超过上限（{MAX_FILES}）", field="url")

        # zip 根目录归一：多个成员可能带公共前缀目录（如 skill/）
        names = [n for n in zf.namelist() if not n.endswith("/")]
        prefix = self._common_prefix(names)
        files: dict[str, bytes] = {}
        for member in names:
            rel = _safe_member_path(member)
            if prefix:
                try:
                    rel = rel.relative_to(prefix)
                except ValueError:
                    continue
            if len(rel.parts) == 0 or any(part == ".." for part in rel.parts):
                raise ValidationException(message=f"zip 成员路径非法: {member}", field="url")
            if len(rel.parts) > MAX_DEPTH + 1:
                raise ValidationException(message=f"目录深度超过上限（{MAX_DEPTH}）: {member}", field="url")
            data = zf.read(member)
            if len(data) > FILE_MAX_BYTES:
                raise ValidationException(message=f"单文件超过大小上限: {member}", field="url")
            files[rel.as_posix()] = data
        if not any(k == "SKILL.md" for k in files):
            raise ValidationException(message="zip 内未找到 SKILL.md", field="url")
        return files

    @staticmethod
    def _common_prefix(names: list[str]) -> Optional[Path]:
        if not names:
            return None
        parts_list = [PurePosixPath(n).parts for n in names]
        first = parts_list[0]
        if len(first) <= 1:
            return None
        prefix = []
        for idx in range(len(first) - 1):
            candidate = first[idx]
            if all(len(p) > idx + 1 and p[idx] == candidate for p in parts_list):
                prefix.append(candidate)
            else:
                break
        return Path(*prefix) if prefix else None

    async def _fetch_github_subdir(self, match: re.Match, client: httpx.AsyncClient) -> dict[str, bytes]:
        owner, repo, ref, subdir = match.group(1), match.group(2), match.group(3), match.group(4)
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
        resp = await client.get(tree_url)
        if resp.status_code != 200:
            raise ValidationException(message=f"GitHub tree API 失败（HTTP {resp.status_code}）", field="url")
        entries = [e for e in resp.json().get("tree", [])
                   if e.get("type") == "blob" and e["path"].startswith(subdir)]
        entries = entries[:MAX_FILES]
        if not entries:
            raise ValidationException(message=f"目录下没有文件: {subdir}", field="url")
        files: dict[str, bytes] = {}
        for entry in entries:
            rel = entry["path"][len(subdir):].lstrip("/")
            depth = len(PurePosixPath(rel).parts)
            if depth > MAX_DEPTH + 1:
                continue
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{entry['path']}"
            files[rel] = await self._fetch_raw(raw_url, client)
        if "SKILL.md" not in files:
            raise ValidationException(message="子目录下未找到 SKILL.md", field="url")
        return files

    # ---------- 解析 / 冲突 ----------

    def _extract_skill(self, files: dict[str, bytes], url: str) -> tuple[str, str]:
        skill_md = files.get("SKILL.md")
        if skill_md is None:
            raise ValidationException(message="来源缺少 SKILL.md", field="url")
        text = skill_md.decode("utf-8", errors="replace")
        frontmatter = _parse_frontmatter(text)
        fallback = Path(urlparse(url).path).stem or "imported-skill"
        name = str(frontmatter.get("name") or re.sub(r"[^a-z0-9\-]", "-", fallback.lower())).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9\-_]{1,127}", name):
            raise ValidationException(message=f"技能名不合法（目录名规范）: {name}", field="url")
        return name, text

    async def _ensure_no_conflict(self, name: str, category: str) -> None:
        existing = (
            await self.session.execute(select(Skill).where(Skill.name == name))
        ).scalar_one_or_none()
        if existing is not None:
            raise ValidationException(message=f"技能名已存在: {name}（请改名或换类目）", field="url")

    async def _similar_candidates(self, name: str, category: str) -> list[str]:
        import difflib

        rows = (
            await self.session.execute(
                select(Skill.name).where(Skill.category == category)
            )
        ).scalars().all()
        return [
            other for other in rows
            if difflib.SequenceMatcher(None, name, other).ratio() > 0.6
        ][:5]

    # ---------- 落盘 / 入库 / 入队 ----------

    def _write_to_library(
        self, name: str, files: dict[str, bytes], url: str,
        category: Optional[str], industries: Optional[list[str]],
    ) -> Path:
        from config import settings

        library_root = Path(str(settings.get("SKILLS.LIBRARY_ROOT", "capability-library")))
        skill_dir = library_root / "skills" / name
        if skill_dir.exists():
            raise ValidationException(message=f"目标目录已存在: {skill_dir}", field="url")
        skill_dir.mkdir(parents=True)
        try:
            for rel, data in files.items():
                target = _safe_member_path(rel)
                dest = skill_dir.joinpath(*target.parts)
                if not dest.resolve().is_relative_to(skill_dir.resolve()):
                    raise ValidationException(message=f"越界写入拒绝: {rel}", field="url")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)

            content_hash = hashlib.sha256(b"".join(
                files[k] for k in sorted(files)
            )).hexdigest()
            today = date.today().isoformat()
            (skill_dir / "SOURCE.md").write_text(
                f"# 来源\n\n- URL: {url}\n- 导入时间: {today}\n"
                f"- content_hash: {content_hash[:12]}…\n",
                encoding="utf-8",
            )
            (skill_dir / "meta.yaml").write_text(
                yaml.safe_dump({
                    "name": name,
                    "category": category or "uncategorized",
                    "industries": industries or [],
                    "status": "experimental",
                    "similar_to": [],
                    "source": {"url": url, "author": "", "imported_at": today, "content_hash": ""},
                    "capability": {
                        "score": None, "ai_suggested_score": None, "rubric": {},
                        "reviewed_by": None, "reviewed_at": None, "notes": None,
                    },
                }, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            (skill_dir / "CHANGELOG.md").write_text(
                f"# 更新记录\n\n- {today} | system | URL 导入: {url}\n",
                encoding="utf-8",
            )
        except Exception:
            import shutil

            shutil.rmtree(skill_dir, ignore_errors=True)
            raise
        return skill_dir

    async def _ingest_and_enqueue(self, name: str, skill_dir: Path) -> None:
        from backend.services.skill_scoring_service import SkillScoringService
        from backend.services.skill_service import SkillService

        await SkillService(self.session).scan_library(root=skill_dir.parent)
        self.session.add(
            SkillJob(
                job_type="import", status="done", total=1, succeeded=1, failed=0,
                detail={"name": name},
            )
        )
        await self.session.flush()
        try:
            await SkillScoringService.enqueue_rescore(name)
        except Exception as exc:  # noqa: BLE001 队列不可用不阻断导入
            logger.warning(f"导入后评分入队失败（忽略） | skill={name} err={exc}")

    # ---------- 检查更新（3.2-A-8：httpx + trust_env=False） ----------

    async def check_update(self, name: str) -> dict:
        """只读拉取 source.url → 与本地 SKILL.md 哈希比对 → 返回是否有更新（不写盘）"""
        row = (await self.session.execute(select(Skill).where(Skill.name == name))).scalar_one_or_none()
        if row is None:
            from platform_core.exceptions import NotFoundException

            raise NotFoundException(resource=f"技能 {name}")
        if not row.source_url:
            return {"name": name, "has_update": None, "reason": "无来源地址"}
        local_md = self._local_skill_md(row)
        if local_md is None:
            return {"name": name, "has_update": None, "reason": "本地无 SKILL.md"}

        client = _make_client()
        try:
            resp = await client.get(row.source_url)
        finally:
            await client.aclose()
        if resp.status_code != 200:
            return {"name": name, "has_update": None, "reason": f"远端 HTTP {resp.status_code}"}
        remote_hash = hashlib.sha256(resp.content).hexdigest()
        local_hash = hashlib.sha256(local_md.encode("utf-8")).hexdigest()
        return {
            "name": name,
            "has_update": remote_hash != local_hash,
            "remote_hash": remote_hash[:12],
            "local_hash": local_hash[:12],
        }

    def _local_skill_md(self, row: Skill) -> Optional[str]:
        from config import settings

        md = Path(str(settings.get("SKILLS.LIBRARY_ROOT", "capability-library"))) / row.file_path / "SKILL.md"
        try:
            return md.read_text(encoding="utf-8") if md.exists() else None
        except OSError:
            return None
