---
name: coding-style
description: 编码规范 - 命名、格式化、类型注解
---

# 编码规范

本规范定义项目的命名和编码准则。

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

**后端**：`black` + `isort`，禁止手动排版

**前端**：`ESLint + Prettier`

## 代码约束

### 后端

- **禁止魔法值**：数字和字符串必须提取为常量
- **异常处理**：捕获具体异常，不抛裸异常
- **函数长度**：单函数 ≤ 40 行，单文件 ≤ 500 行
- **类型注解**：所有函数必须添加类型提示

### 前端

- **TypeScript**：禁止 `any`
- **组件拆分**：单组件 ≤ 300 行
- **状态管理**：优先 Context + useReducer

### 爬虫

- **反爬策略**：每个爬虫必须至少实现随机延迟 + UA 轮换
- **数据质量**：爬取后立即校验必填字段
- **通信方式**：数据丢了能重爬→Redis；不能→MQ

## 注释规范

- **后端接口**：文档字符串，自动生成 Swagger
- **数据模型**：字段添加 `comment`
- **复杂逻辑**：解释"为什么"而非"做了什么"
- **禁止**：无意义注释、注释代码不删除、中英文混杂
