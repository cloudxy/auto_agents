#!/usr/bin/env bash
cd /Users/xuyun/auto_agents
E=.sdlc/_review/2026-09-27-project-audit/evidence
export APP_ENV=local AUTO_AGENTS_JWT__SECRET_KEY=ci-test-secret-key-not-for-production AUTO_AGENTS_WEBHOOK__SECRET_KEY=ci-test-webhook-secret
{ echo "\$ bash tools/check/frontend.sh"; bash tools/check/frontend.sh; echo "exit=$?"; } > $E/frontend-gate.txt 2>&1
{ echo "\$ npm run build -w @auto-agents/frontend-shared"; npm run build -w @auto-agents/frontend-shared; echo "exit=$?"; for a in admin official; do echo "\$ npx tsc --noEmit -p frontend/$a"; npx tsc --noEmit -p frontend/$a; echo "exit=$?"; echo "\$ CI= npm run build -w $a"; CI= npm run build -w $a; echo "exit=$?"; done; } > $E/frontend-build.txt 2>&1
for a in admin official; do { echo "\$ CI=true npm test -w $a"; date; CI=true npm test -w $a -- --watchAll=false 2>&1 | tail -80; echo "exit=${PIPESTATUS[0]}"; date; } > $E/frontend-test-$a.txt 2>&1; done
echo done > $E/fe.done
