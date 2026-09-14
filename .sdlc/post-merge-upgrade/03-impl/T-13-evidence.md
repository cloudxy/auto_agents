# 实现证据 · T-13 出站拉数钥匙产品名与第二平面 404

> 票：contract §10 T-13｜FR 锚点：FR-M20｜角色：/frontend（lane: ui）｜日期：2026-09-13

## 1. 契约落位表（UI 面）

| 契约元素 | 落在哪 | 文件 | 备注 |
|---|---|---|---|
| 产品名只「出站拉数钥匙」 | 菜单 + 页内 Card | `menuConfig.tsx` / `OutboundKeys.tsx` | 无第二标题「API 钥匙」 |
| 空态金标 | LoadEmpty 同句 | `EMPTY_FALLBACK` | 「还没有出站拉数钥匙。签发后才能从外部系统拉本企业结果。」 |
| 第二钥匙 URL 404 同形不重定向 | 路由无 `/api-keys` | `App.tsx` `path=*` → `NotFound` | 不 `Navigate` 到 `/outbound-keys` |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/OutboundKeys.test.tsx` | 修改 | GWT-M20 产品名 |
| `frontend/admin/src/App.menu.test.tsx` | 修改 | `/api-keys` `/api_keys` 404 同形 |

产品页既有金标与产品名；本票钉测试 + 确认无第二路由。

## 3. 自测证据

```
$ cd frontend/admin && CI=true npx jest src/pages/OutboundKeys.test.tsx src/App.menu.test.tsx --maxWorkers=2
PASS src/pages/OutboundKeys.test.tsx
PASS src/App.menu.test.tsx
exit: 0
```

合跑 W3 六套：`Tests: 81 passed, 81 total` / exit 0。`bash tools/check/frontend.sh` EXIT:0。

| GWT | 测试 | 结果 |
|---|---|---|
| 空态金标 | gwt_51_2 | ✅ |
| 产品名唯一 | GWT-M20 product name | ✅ |
| 第二 URL 404 不跳转 | GWT-M20 /api-keys /api_keys | ✅ pathname 仍为原 path |

## 4. 给下游

| 给谁 | 内容 |
|---|---|
| `/qa` | 租户打 `/api-keys` 与缺页同壳；工作台不出站页 |
| `/backend` | 拉数命中集合仍须只认出站签发（T-12） |

## 5. 交票自检

- [x] jest + exit
- [x] 无「当前可买」
- [x] 未做值班折叠
