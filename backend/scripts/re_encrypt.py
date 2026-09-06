#!/usr/bin/env python3
"""Fernet 主密钥轮换：用旧钥解密 llm_providers.api_key 再用新钥写回。"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate LLM_ENCRYPTION_KEY")
    parser.add_argument("--old-key", required=True, help="当前 Fernet 密钥")
    parser.add_argument("--new-key", required=True, help="新 Fernet 密钥")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    from cryptography.fernet import Fernet
    from sqlalchemy import select

    from platform_core.db import get_manager
    from platform_core.models.llm_provider import LlmProvider

    old_f, new_f = Fernet(args.old_key.encode()), Fernet(args.new_key.encode())
    mgr = get_manager()
    session = mgr.get_session()
    rows = session.execute(select(LlmProvider)).scalars().all()
    n = 0
    for row in rows:
        raw = getattr(row, "api_key", None)
        if not raw:
            continue
        try:
            plain = old_f.decrypt(raw.encode() if isinstance(raw, str) else raw)
        except Exception as exc:  # noqa: BLE001
            print(f"skip id={row.id}: {exc}")
            continue
        if not args.dry_run:
            row.api_key = new_f.encrypt(plain).decode()
        n += 1
    if not args.dry_run:
        session.commit()
    print(f"re-encrypted {n} provider keys dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
