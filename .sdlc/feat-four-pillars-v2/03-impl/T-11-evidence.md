# T-11 证据 · 密钥离树

> 泳道：L4
> 票：T-11 · FR-14 / GWT-14.1–14.5 · NFR-04
> 角色：sre
> 日期：2026-09-08
> 闸：`git ls-files deploy/litellm/config.gen.yaml`；`bash tools/check/arch.sh`
> 本文件不含任何上游 Key 明文。

## 范围

做了：生成网关配置离树、ignore、跟踪树样例模式扫描 0 命中、管理详情对非超管去掉本机绝对路径、租户设置掩码合同保持。

没做：不启 LiteLLM、不改 `llm_chat` 出口、不把网关写进根编排、不打开 new-api、不写 `06-deliver/checklist.md` 正文、不代选六问、不实现 T-14。GWT-14.3 不把「打开渠道页见掩码」当 Then。

## 闸输出

### `git ls-files deploy/litellm/config.gen.yaml`

（空：0 行）

同目录现跟踪：`deploy/litellm/.gitignore`、`deploy/litellm/config.yaml.example`。本地 `config.gen.yaml` 仍在工作区，已被 ignore（`deploy/litellm/.gitignore` 的 `*.gen.yaml`）。

### `bash tools/check/arch.sh`

FR-14 段：

```
--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式
```

整脚本退出码 **1**。非 T-11 引入：R10 命中并行票 T-04 工作区函数 `backend/services/audit_service.py` `record_authz_denied`（多行签名，下一行不是 `logger.`）。T-11 未改该文件。FR-14 两行均为 ✓。

## GWT

| GWT | Then | 本票证据 |
|---|---|---|
| 14.1 | 超管打开管理详情查看能力，不把本机绝对路径当作租户可复制字段发出给非超管 | `omit_local_abs_paths_for_non_platform_admin`；`test_capability_detail_superadmin_abs_path_not_emitted_to_tenant` |
| 14.2 | 租户打开管理详情（若允许读）无本机路径 | `test_capability_detail_tenant_omits_local_absolute_path`；相对路径仍可返回（`test_capability_detail_keeps_relative_path_for_tenant`） |
| 14.3 | 租户直打中转页走 GWT-07.3，页上无密钥 | **T-05**。禁止用「打开渠道页见掩码」当本 FR 的 Then。本票不改渠道页。 |
| 14.4 | 租户打开自己仍能进的系统设置且其中有密钥字段，查看仅掩码 | 现网 `/llm` 已是 `api_key_masked`；`TestMask` + `TestApiEndpoints::test_list_endpoint_direct_array_masked` 同 PR 保持 |
| 14.5 | 跟踪样例无真实上游 Key 明文；`config.gen.yaml` 不在跟踪树 | ignore + `git rm --cached`；样例 `config.yaml.example` 仅 `os.environ/OPENAI_API_KEY`；扫描模式由 `sk` + `-` 拼接，测试/脚本/CI 不写真密钥 |

## 同 PR 测试

```
uv run pytest -x -q \
  backend/tests/test_fr14_secrets_off_tree.py \
  backend/tests/test_llm_provider.py::TestMask \
  backend/tests/test_llm_provider.py::TestApiEndpoints::test_list_endpoint_direct_array_masked \
  backend/tests/test_b1c_capabilities_coverage.py::test_capability_detail_ok_and_404 \
  backend/tests/test_skills_api.py::test_get_skill_detail_includes_files_and_reviews
```

`15 passed in 1.59s` 退出码 0。

扫描：`git grep -lE` 只打文件名；`deploy/` + `config/`；无命中时 git grep 退出 1。

## 轮换（清单项，不写密钥）

交付清单（后续 `06-deliver/checklist.md`，本票不写该文件）必须含：

1. 轮换曾出现在已跟踪生成配置里的上游凭据（操作者机外；证据只记「已轮换」，不贴值）。
2. 可选：git 史 `filter-repo` 清已提交明文——操作者机外，本票不执行。
3. 之后生成配置只走 ignore + 运行时注入（T-14）。

## 未做 / 边界

- T-14 compose、镜像 tag、根编排 external 网、启网关。
- T-05 直打中转 404 同形。
- T-04 平台写面守卫 / `record_authz_denied` R10。
- `frontend/official/**`、`backend/app/tenant_isolation.py`、平台管理路由改写、官网文案。
