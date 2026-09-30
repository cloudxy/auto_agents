#!/usr/bin/env bash
cd /Users/xuyun/auto_agents
E=.sdlc/_review/2026-09-27-project-audit/evidence
export APP_ENV=local AUTO_AGENTS_JWT__SECRET_KEY=ci-test-secret-key-not-for-production AUTO_AGENTS_WEBHOOK__SECRET_KEY=ci-test-webhook-secret
{ echo "\$ uv run ruff check backend platform_core scripts"; uv run ruff check backend platform_core scripts; echo "exit=$?"; } > $E/ruff.txt 2>&1
{ echo "\$ uv run ruff check --select E,F,B,UP,SIM,ASYNC --statistics backend platform_core scrapy scripts run.py"; uv run ruff check --select E,F,B,UP,SIM,ASYNC --statistics backend platform_core scrapy scripts run.py; echo "exit=$?"; } > $E/ruff-extended.txt 2>&1
{ echo "\$ bash tools/check/arch.sh"; bash tools/check/arch.sh; echo "exit=$?"; } > $E/arch.txt 2>&1
{ echo "\$ bash tools/check/db_ir.sh"; bash tools/check/db_ir.sh; echo "exit=$?"; echo "\$ bash tools/check/db_migrations.sh"; bash tools/check/db_migrations.sh; echo "exit=$?"; } > $E/db-gates.txt 2>&1
{ echo "\$ uv run pytest -q --tb=short -p no:cacheprovider --durations=20 --cov=backend --cov=platform_core --cov-report=term backend/tests"; date; uv run pytest -q --tb=short -p no:cacheprovider --durations=20 --cov=backend --cov=platform_core --cov-report=term backend/tests; echo "exit=$?"; date; } > $E/pytest.txt 2>&1
echo done > $E/py.done
