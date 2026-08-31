#!/usr/bin/env python3
"""Skills-library 本地管理后台。仅监听 127.0.0.1，不对外暴露。

- GET  /api/skills                     列表(支持 category/industry/status 筛选)
- GET  /api/skills/{name}               详情 (meta.yaml + SKILL.md frontmatter + SOURCE.md + CHANGELOG.md)
- PUT  /api/skills/{name}/meta          编辑 meta.yaml 治理字段 -> 写回文件 -> 重建索引
- POST /api/skills/{name}/check-update  只读拉取 source.url，返回哈希对比结果，不写文件
- POST /api/skills/{name}/changelog     追加一条更新记录到 CHANGELOG.md
- GET  /api/skills/{name}/compare       同 category 内多个 skill 并排对比
- POST /api/sync                        调用 sync.sh 落地到各工具
- GET  /api/manifests/{tool}            查看某工具启用的 skill 列表
- PUT  /api/manifests/{tool}            编辑某工具启用的 skill 列表
- GET  /api/taxonomy                    industries.yaml + rubric.md 内容

用法: python3 backend/app.py <skills-library-root> [--port 8765]
"""
import hashlib
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT: Path
app = FastAPI(title="skills-library backend")


def skill_dir(name: str) -> Path:
    d = ROOT / "skills" / name
    if not d.is_dir():
        raise HTTPException(404, f"skill not found: {name}")
    return d


def load_meta(name: str) -> dict:
    p = skill_dir(name) / "meta.yaml"
    if not p.is_file():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def save_meta(name: str, meta: dict) -> None:
    p = skill_dir(name) / "meta.yaml"
    p.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")


def read_frontmatter(name: str) -> dict:
    p = skill_dir(name) / "SKILL.md"
    if not p.is_file():
        return {}
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    return yaml.safe_load(text[4:end]) or {}


def rebuild_index() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "index" / "build_index.py"), str(ROOT)],
        check=True,
    )


@app.get("/api/skills")
def list_skills(category: Optional[str] = None, industry: Optional[str] = None, status: Optional[str] = None):
    out = []
    skills_root = ROOT / "skills"
    if not skills_root.is_dir():
        return out
    for d in sorted(skills_root.iterdir()):
        if not d.is_dir():
            continue
        meta = load_meta(d.name)
        if category and meta.get("category") != category:
            continue
        if status and meta.get("status") != status:
            continue
        industries = meta.get("industries") or []
        if industry and industry not in industries:
            continue
        fm = read_frontmatter(d.name)
        out.append(
            {
                "name": d.name,
                "description": fm.get("description"),
                "category": meta.get("category"),
                "industries": industries,
                "status": meta.get("status"),
                "score": (meta.get("capability") or {}).get("score"),
                "similar_to": meta.get("similar_to") or [],
            }
        )
    return out


@app.get("/api/skills/{name}")
def get_skill(name: str):
    d = skill_dir(name)
    meta = load_meta(name)
    fm = read_frontmatter(name)
    source_md = (d / "SOURCE.md").read_text(encoding="utf-8") if (d / "SOURCE.md").is_file() else ""
    changelog = (d / "CHANGELOG.md").read_text(encoding="utf-8") if (d / "CHANGELOG.md").is_file() else ""
    skill_md = (d / "SKILL.md").read_text(encoding="utf-8") if (d / "SKILL.md").is_file() else ""
    return {
        "name": name,
        "meta": meta,
        "frontmatter": fm,
        "skill_md": skill_md,
        "source_md": source_md,
        "changelog": changelog,
    }


class MetaUpdate(BaseModel):
    category: Optional[str] = None
    industries: Optional[list] = None
    status: Optional[str] = None
    similar_to: Optional[list] = None
    capability: Optional[dict] = None


@app.put("/api/skills/{name}/meta")
def update_meta(name: str, body: MetaUpdate):
    skill_dir(name)  # 404 检查
    meta = load_meta(name)
    patch = body.model_dump(exclude_unset=True)
    for k, v in patch.items():
        if k == "capability" and isinstance(meta.get("capability"), dict) and isinstance(v, dict):
            meta["capability"].update(v)
        else:
            meta[k] = v
    save_meta(name, meta)
    rebuild_index()
    return {"ok": True, "meta": meta}


@app.post("/api/skills/{name}/check-update")
def check_update(name: str):
    """只读拉取 source.url 内容并算哈希，跟 meta.yaml 里存的对比，不写任何文件。"""
    meta = load_meta(name)
    url = (meta.get("source") or {}).get("url")
    if not url:
        raise HTTPException(400, "该 skill 没有配置 source.url，无法检查更新")
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 - 用户主动触发的只读请求
            content = resp.read()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"拉取源地址失败: {e}")
    new_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    old_hash = (meta.get("source") or {}).get("content_hash")
    return {"old_hash": old_hash, "new_hash": new_hash, "changed": old_hash != new_hash}


class ChangelogEntry(BaseModel):
    author: str
    summary: str


@app.post("/api/skills/{name}/changelog")
def add_changelog(name: str, entry: ChangelogEntry):
    d = skill_dir(name)
    p = d / "CHANGELOG.md"
    existing = p.read_text(encoding="utf-8") if p.is_file() else "# 更新记录\n\n"
    line = f"- {date.today().isoformat()} | {entry.author} | {entry.summary}\n"
    p.write_text(existing.rstrip("\n") + "\n" + line, encoding="utf-8")
    return {"ok": True}


@app.get("/api/skills/{name}/compare")
def compare(name: str, with_skill: str = Query(..., alias="with")):
    names = [name, with_skill]
    out = []
    for n in names:
        meta = load_meta(n)
        fm = read_frontmatter(n)
        out.append(
            {
                "name": n,
                "description": fm.get("description"),
                "category": meta.get("category"),
                "capability": meta.get("capability"),
                "status": meta.get("status"),
            }
        )
    return out


@app.post("/api/sync")
def run_sync():
    result = subprocess.run(
        ["bash", str(ROOT / "sync.sh"), "--reindex"],
        capture_output=True,
        text=True,
    )
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


@app.get("/api/manifests/{tool}")
def get_manifest(tool: str):
    p = ROOT / "manifests" / f"{tool}.yaml"
    if not p.is_file():
        raise HTTPException(404, f"manifest not found: {tool}")
    names = [
        line.strip()[2:].strip().strip('"').strip("'")
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- ")
    ]
    return {"tool": tool, "skills": names}


class ManifestUpdate(BaseModel):
    skills: list[str]


@app.put("/api/manifests/{tool}")
def put_manifest(tool: str, body: ManifestUpdate):
    p = ROOT / "manifests" / f"{tool}.yaml"
    header = f"# {tool} 启用的 skill 列表，每行一个 skill 名（对应 skills/<name>/ 目录）\n"
    if p.is_file():
        # 保留原有注释头（首个非 "- " 开头的连续行块）
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        comment_lines = [ln for ln in lines if not ln.strip().startswith("- ")]
        if comment_lines:
            header = "".join(comment_lines)
            if not header.endswith("\n"):
                header += "\n"
    body_text = "".join(f"- {s}\n" for s in body.skills)
    p.write_text(header + body_text, encoding="utf-8")
    return {"ok": True}


@app.get("/api/taxonomy")
def get_taxonomy():
    industries_path = ROOT / "taxonomy" / "industries.yaml"
    rubric_path = ROOT / "taxonomy" / "rubric.md"
    industries = yaml.safe_load(industries_path.read_text(encoding="utf-8")) if industries_path.is_file() else []
    rubric = rubric_path.read_text(encoding="utf-8") if rubric_path.is_file() else ""
    return {"industries": industries, "rubric_md": rubric}


@app.get("/")
def index_html():
    return FileResponse(str(Path(__file__).parent / "web" / "index.html"))


def main():
    global ROOT
    if len(sys.argv) < 2:
        print("usage: app.py <skills-library-root> [--port 8765]", file=sys.stderr)
        sys.exit(1)
    ROOT = Path(sys.argv[1]).resolve()
    port = 8765
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])

    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "web")), name="static")

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
