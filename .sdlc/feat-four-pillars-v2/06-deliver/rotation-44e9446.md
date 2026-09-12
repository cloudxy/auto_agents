# 44e9446 上游凭据轮换证据 · feat-four-pillars-v2

> 作者：/sre｜日期：2026-09-10｜泳道：L4
> **本文件只列提供商与跟踪状态。禁止写入任何 api_key / sk- 值 / 密文片段。**
> 本帽 **不得** 勾选「已轮换」。轮换在提供商控制台、机外完成；证据由操作者落一行日期。

## 1. 史：明文进树

| 项 | 值 |
|---|---|
| commit | `44e944641f62f0f5a7f49372627e1ffc3a5e68fc`（短 `44e9446`） |
| 日期 | 2026-09-07 09:13:17 +0800 |
| subject | `deploy:litellm` |
| 文件 | `deploy/litellm/config.gen.yaml`（该提交 `+40` 行） |
| `api_key:` 行 | **7** 行，全部明文 `sk-…`（0 行 `os.environ`） |
| 值 | **不复制、不摘前缀以外的分类信息** |

7 行分布（仅 api_base / 模型 id，无密钥）：

| 提供商 | api_base | 模型数 | litellm `model` id（非密钥） |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | 3 | `openai/deepseek-v4-flash` · `openai/deepseek-v4-pro` · `openai/deepseek-v4-flash-vision-exp` |
| Moonshot / Kimi | `https://api.moonshot.cn/v1` | 4 | `openai/kimi-k3` · `openai/kimi-k2.6` · `openai/kimi-k2.7-code` · `openai/kimi-k2.7-code-highspeed` |

Git 历史仍含该 blob。`git rm --cached` / ignore **不能** 当作密钥作废。

## 2. 须在提供商控制台轮换

| 提供商 | 动作（机外） |
|---|---|
| DeepSeek | 作废并轮换曾进 `44e9446` 的上游 Key（3 模型共用一类凭据） |
| Moonshot / Kimi | 作废并轮换曾进 `44e9446` 的上游 Key（4 模型共用一类凭据） |

轮换完成后：本地生成配置只许 `api_key: os.environ/<NAME>`；禁止再把明文写进任何入库文件。

## 3. 当前树（跟踪）

```
$ git ls-files deploy/litellm/config.gen.yaml
```

（空，0 行）— 索引已不跟踪。

```
$ bash tools/check/arch.sh
--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
```

当前跟踪树（`b8b5f85`，2026-09-10）：

- `git ls-tree HEAD -- deploy/litellm/config.gen.yaml` **空**（untrack 已入库）。Git **历史** `44e9446` 仍含该 blob；untrack ≠ 凭据作废。
- 工作树仍有 gitignored `deploy/litellm/config.gen.yaml`（mode 600）。**未打开、未摘录。** 轮换后由操作者改成 env 引用或删除。
- `deploy/litellm/.gitignore` 含 `config.gen.yaml` / `*.gen.yaml`。

跟踪修复 ≠ 凭据作废。

## 4. 操作者证明

操作者 2026-09-10 明示：Kimi 与 DeepSeek 的 Key 已全部修改。本文件只记日期，不写密钥。

```
rotated: 2026-09-10
```

| 项 | 状态 |
|---|---|
| DeepSeek 已轮换 | ☑ 操作者机外完成（2026-09-10） |
| Moonshot / Kimi 已轮换 | ☑ 操作者机外完成（2026-09-10） |
| 证明行 `rotated: YYYY-MM-DD` | **rotated: 2026-09-10** |

先前延期句（「没有更换key，因为能够使用」）被本轮操作者声明覆盖。新 Key 只许活在本机 env / gitignore 配置，禁止再入库。

## 5. 闸门（条件 A）

| 半格 | 证据 | 状态 |
|---|---|---|
| dockerd `compose down --remove-orphans` | 本帽独立 2026-09-10T03:53:38Z `DOWN_EXIT:0`（`docker info` 0；sock `~/.docker/run/docker.sock`；两条 `config -q` 0；`:4000` 无监听；compose ps 空）。先前 02:43:36Z exit 1（当时 daemon 未起）不作本半格 | **PASS** |
| 机外轮换 `44e9446` | 操作者 2026-09-10：Kimi 与 DeepSeek Key 已全部修改。`rotated: 2026-09-10`。无密钥入库 | **PASS** |

条件 A 整体 **PASS**（down + 轮换日期行）。不是四柱 GA。仓库默认仍 `LLM.ENABLED: false`；本机可用 `AUTO_AGENTS_LLM__ENABLED=true` 打开。根 compose 仍禁止焊 litellm 服务。新 Key 禁止提交。
