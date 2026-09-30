#!/usr/bin/env bash
cd /Users/xuyun/auto_agents
E=.sdlc/_review/2026-09-27-project-audit/evidence
{ echo "\$ uv run pip-audit"; uv run pip-audit 2>&1 | tail -60; echo "exit=${PIPESTATUS[0]}"; } > $E/pip-audit.txt 2>&1
{ echo "\$ npm audit --omit=dev"; npm audit --omit=dev 2>&1 | tail -60; echo "exit=${PIPESTATUS[0]}"; } > $E/npm-audit.txt 2>&1
{ echo "\$ uv tree --outdated --depth 1"; uv tree --outdated --depth 1 2>&1 | grep -i latest | head -60; } > $E/uv-outdated.txt 2>&1
echo done > $E/audit.done
