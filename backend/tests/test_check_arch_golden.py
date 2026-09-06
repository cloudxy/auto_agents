"""E3：R10 规则黄金样例（违规 vs 干净）；I2 宣称锚点文件存在。"""
import re
from pathlib import Path


def _r10_hits(source: str) -> list[str]:
    lines = source.splitlines()
    hits = []
    for i, line in enumerate(lines):
        if re.match(r"^(async )?def [a-z]", line):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if "logger." not in nxt:
                hits.append(line)
    return hits


def test_r10_flags_missing_logger():
    hits = _r10_hits("def create_thing():\n    return 1\n")
    assert any("create_thing" in h for h in hits)


def test_r10_clean_when_logger_first():
    assert _r10_hits("def create_thing():\n    logger.info('x')\n    return 1\n") == []


def test_claims_anchor_files_exist():
    root = Path(__file__).resolve().parents[2]
    claims = (root / "docs/claims.md").read_text(encoding="utf-8")
    for line in claims.splitlines():
        if "`backend/" in line or "`frontend/" in line:
            start = line.index("`") + 1
            end = line.index("`", start)
            rel = line[start:end].split()[0]
            assert (root / rel).is_file(), rel
