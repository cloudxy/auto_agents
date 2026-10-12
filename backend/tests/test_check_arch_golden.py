"""I2：docs/claims.md 宣称锚点文件存在。

R10 黄金样例已移到 test_check_arch_r10.py——那里直接抽取并执行 arch.sh 里的真实检查块，
此前这里的逐行正则只是测试文件自己的简化实现，测不到真实规则。
"""
from pathlib import Path


def test_claims_anchor_files_exist():
    root = Path(__file__).resolve().parents[2]
    claims = (root / "docs/claims.md").read_text(encoding="utf-8")
    for line in claims.splitlines():
        if "`backend/" in line or "`frontend/" in line:
            start = line.index("`") + 1
            end = line.index("`", start)
            rel = line[start:end].split()[0]
            assert (root / rel).is_file(), rel
