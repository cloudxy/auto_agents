## 摘要

<!-- 做了什么、为什么 -->

## 根因

<!-- 若为修复：缺陷如何产生；若为功能：为何现在做 -->

## 回归用例

<!-- 测试文件::用例名，或「无代码路径 / 文档-only」 -->

- [ ] `backend/tests/…`
- [ ] 前端 Jest / Playwright（路径）
- [ ] 无代码路径 / 文档-only

## 验收对照

<!-- 对应 docs/claims.md 或工单；不要写已删除的 docs/plan/* -->

## 检查

- [ ] `uv run pytest -q backend/tests`
- [ ] `bash scripts/check-arch.sh`
- [ ] 前端改动：`bash scripts/check-frontend.sh` + `CI= npm run build -w {admin|official|@auto-agents/frontend-shared}`
- [ ] 登录 / 看板 / 用量 / 成员：先 build admin，再 `CI=1 npm run e2e -w admin`
- [ ] 增删路由：已更新 `backend/tests/openapi_routes_golden.txt`
- [ ] schema / 迁移：`/db-design` + `bash scripts/check-db-ir.sh` + `bash scripts/check-db-migrations.sh`
