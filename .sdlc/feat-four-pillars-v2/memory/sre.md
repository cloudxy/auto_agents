# sre memory · feat-four-pillars-v2

> Facts (**what**). Procedures in SKILL.md. Cap 2200 chars.

## Last

- Date: 2026-09-10
- Hat: 交付 / 条件 A down 半格 PASS（rotation pending）
- Outputs: `06-deliver/qc-cond-2-preprod.md`；`06-deliver/checklist.md`；`06-deliver/rotation-44e9446.md`
- Gate: `check-sdlc.sh --require --hat deliver` exit 0

## Facts

- 条件 2 **satisfied**：37.6 PASS；NFR-01 Chrome P95 1.444558s；GWT-18.1 Then **PASS** task#2 completed **+40.56s** result_count=1 export 200 rows 1。
- 条件 1/3/4/5 **satisfied**。条件 6 **lock**。不是四柱 GA。
- 条件 A 整体 **not PASS**。down 半格 **PASS**：本帽独立 2026-09-10T03:53:38Z `compose down --remove-orphans` **exit 0**；`docker info` 0 ServerVersion=29.4.0；sock `~/.docker/run/docker.sock`。先前 02:43:36Z exit 1（当时无 daemon）不作本半格。
- `44e9446` 无 `rotated:` 行。本帽不自勾已轮换、不代写日期。证明前禁止 `LLM.ENABLED=true` / litellm compose up。
- Then PASS ≠ 允许 LiteLLM/生产 动工。**动工 = NO**。本帽不改 coverage.md / release-opinion / rotation 勾选。
- Alembic 039 仍 `??`。生产禁止 down past 037。默认 ENABLED=false。根 compose 无 litellm。

## Open (mine)

- 操作者机外轮换后写 `rotated: YYYY-MM-DD`。
- 清理 `nfr01qc2-%`。
- 039 + staged untrack `config.gen.yaml` 随 merge（本帽不 commit）。
- coverage 18.1 翻格交 `/qa`。

## Do not re-litigate

- FakeRedis ≠ 18.1。TestClient ≠ NFR-01。
- 条件 2 satisfied ≠ 四柱 GA ≠ 动工。
- 六问不代选。
- 无 daemon 的 down exit 1 不得粉饰为 PASS。本轮 daemon 已起，down 0 是真 PASS。
- 无 `rotated:` ≠ 已轮换。down PASS ≠ 条件 A PASS。
- 生产禁止 down past 037。根 compose 无 litellm / new-api。
