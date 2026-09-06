---
name: coding-style
description: >-
  编码规范 - 命名、格式化、类型注解。当用户编写、修改或审查 Python 后端、
  前端 TypeScript、Scrapy 爬虫代码时触发。
  适用于新增模块的命名与结构规范、代码审查中的风格一致性检查，
  以及格式化排版、类型注解、魔法值消除、函数长度控制等编码约束的场景。
trigger: >-
  代码审查、命名规范检查、格式化修正、类型注解补全、编码风格统一
---

# 编码规范

## 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| Python 项目/包 | 小写+下划线 | `user_server` |
| Python 模块 | 小写+下划线 | `user_service.py` |
| Python 类 | 大驼峰 | `UserService`, `UserInfoSpider` |
| Python 函数/变量 | 下划线 | `get_user_by_id` |
| Python 常量 | 全大写+下划线 | `MAX_RETRY_COUNT` |
| 爬虫 name | 小写+下划线 | `user_info` |
| Item 类 | 大驼峰+Item | `UserInfoItem` |
| 数据库表/字段 | 小写+下划线 | `user_info` |
| Redis Key | 业务:功能:ID | `user:info:1001` |
| API URL | 小写+短横线 | `/api/v1/user/list` |
| React 组件 | 大驼峰 | `UserList.tsx` |
| React 函数 | 小驼峰 | `formatUserInfo` |
| CSS 文件 | 小写+短横线 | `user-list.module.css` |

## 格式化

**后端**：`ruff`（`pyproject.toml` `[tool.ruff]`，当前 select `E9`+`F401`，target py313）。不要引入 black / isort。

```bash
uv run ruff check backend platform_core scripts
```

**前端**：CRA `eslintConfig`（`react-app`）。仓库没有 Prettier。npm workspaces：`npm run test -w admin`，不要 `cd frontend/admin && npm run build` 当唯一入口。

## 代码约束

### 后端

- **禁止魔法值**：数字和字符串提取为常量或 config
- **异常处理**：捕获具体异常，走 `platform_core.exceptions`
- **函数长度**：单函数 ≤ 40 行，单文件 ≤ 500 行（前端 `.tsx` 门禁见 `scripts/check-frontend.sh`）
- **类型注解**：所有函数必须添加类型提示
- **日志**：service public 方法第一行 `logger.info`（R10）

### 前端

- **TypeScript**：禁止 `any`
- **组件拆分**：单组件 ≤ 300 行
- **客户端状态**：zustand（`useAuthStore`）。不要把全局 auth 做成 Context + useReducer
- **服务端状态**：TanStack `useQuery` / `useQueryClient`；列表页错误/空态用 `QueryStateView`
- **queryFn**：不要把「首参可选」的 API 函数直接当 queryFn（会变成 QueryFunction context，TS2769）
- **信封**：`ApiEnvelope` 只从 `@auto-agents/frontend-shared` 引入（F-6）
- **错误提示**：`message.error` 走 `apiErrorMessage`，antd `Alert` 用 `title` 不是 `message`

### 爬虫

- **反爬**：全局 `DOWNLOAD_DELAY` + UA；不要在 parse 里 `time.sleep`
- **数据出口**：只走 Redis 队列（`StorePipeline`）
- **基类**：`TaskAwareRedisSpider`

## 注释规范

- **后端接口**：文档字符串，进 OpenAPI
- **数据模型**：字段 `comment=`
- **复杂逻辑**：解释"为什么"
- **禁止**：无意义注释、注释代码不删除
