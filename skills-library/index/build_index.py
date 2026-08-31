#!/usr/bin/env python3
"""扫描 skills/*/{SKILL.md, meta.yaml} 重建 index/index.db。

index.db 是纯派生缓存，删除后重跑本脚本即可重建，不是权威数据源。
权威数据源始终是 skills/<name>/{SKILL.md,meta.yaml,SOURCE.md,CHANGELOG.md}。

用法: build_index.py <skills-library-root>
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("需要 PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def load_meta(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def build(root: Path) -> int:
    skills_dir = root / "skills"
    db_path = root / "index" / "index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS skills")
    conn.execute(
        """
        CREATE TABLE skills (
            name TEXT PRIMARY KEY,
            description TEXT,
            category TEXT,
            industries TEXT,      -- JSON array
            score REAL,
            ai_suggested_score REAL,
            status TEXT,
            similar_to TEXT,      -- JSON array
            source_url TEXT,
            source_author TEXT,
            imported_at TEXT,
            content_hash TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            notes TEXT
        )
        """
    )

    count = 0
    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            meta_yaml = skill_dir / "meta.yaml"
            fm = parse_frontmatter(skill_md.read_text(encoding="utf-8")) if skill_md.is_file() else {}
            meta = load_meta(meta_yaml)

            cap = meta.get("capability", {}) or {}
            source = meta.get("source", {}) or {}

            def s(v):
                """yaml 会把裸日期解析成 date 对象，sqlite3 新版不再自动适配，统一转 str。"""
                return str(v) if v is not None else None

            conn.execute(
                """
                INSERT OR REPLACE INTO skills VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    meta.get("name") or fm.get("name") or skill_dir.name,
                    fm.get("description"),
                    meta.get("category"),
                    json.dumps(meta.get("industries") or [], ensure_ascii=False),
                    cap.get("score"),
                    cap.get("ai_suggested_score"),
                    meta.get("status"),
                    json.dumps(meta.get("similar_to") or [], ensure_ascii=False),
                    source.get("url"),
                    source.get("author"),
                    s(source.get("imported_at")),
                    source.get("content_hash"),
                    cap.get("reviewed_by"),
                    s(cap.get("reviewed_at")),
                    cap.get("notes"),
                ),
            )
            count += 1

    conn.commit()
    conn.close()
    return count


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: build_index.py <skills-library-root>", file=sys.stderr)
        sys.exit(1)
    n = build(Path(sys.argv[1]).resolve())
    print(f"indexed {n} skills -> index/index.db")
