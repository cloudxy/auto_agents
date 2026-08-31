# 归档说明：spiders 路由拆包契约基线（2026-08-30）

spiders 路由按领域拆包（task / query / registry / control 子路由）后，为证明
**拆包未改变对外 API 契约**，归档拆包前后的 OpenAPI 证据快照。
关联背景：S12 门面 import 白名单规则见 `scripts/check-arch.sh` R12。

## 归档文件

| 文件 | 来源（temp/，未删除） | 内容 |
|------|----------------------|------|
| `openapi_baseline.json` | `openapi_full_before.json` | 拆包前全量 OpenAPI（60 paths，170,718 字节） |
| `openapi_spiders_paths_before.json` | `openapi_spiders_before.json` | 拆包前路由清单：path → HTTP methods 映射（60 paths / 72 ops） |

## 证据要点

1. **拆包前后 OpenAPI 字节级一致**：拆包前全量快照与拆包后全量快照
   `cmp` 无差异（均为 60 paths / 170,718 字节），对外契约零变更。
2. **三份全量快照相互 cmp 相同**（去重依据，仅归档一份 baseline）：
   - `temp/openapi_full_before.json`（2026-08-30 23:41）
   - `temp/openapi_spiders_before_fresh.json`（2026-08-31 00:06，新鲜重采）
   - `temp/openapi_spiders_after.json`（2026-08-31 00:07，拆包后）
3. 路由清单快照覆盖拆包前全部 60 paths / 72 ops（含 spiders 域 29 条），
   可与拆包后路由表 diff 佐证路径与方法无增删。

## 校验和（SHA-256）

```
dd180296e29b7d2934d899804cf363906dc10b0a54db254f75f3be11a9e2dd13  openapi_baseline.json
6de573871a339d5990437c3f5c5213c481227ccea1299a04af4a6f32a5f51ab3  openapi_spiders_paths_before.json
```

## 归档信息

- 归档时间：2026-08-31
- 来源生成窗口：2026-08-30 23:41 – 2026-08-31 00:07
- 来源目录：`temp/`（运行期产物，不入库；快照仅复制归档，源文件保留）
