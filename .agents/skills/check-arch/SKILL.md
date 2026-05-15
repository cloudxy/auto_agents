---
name: check-arch
description: 架构合规检查 - 一键扫描 project_rule.md 的 10 条红线违规，输出违规文件:行号报告
---

# 架构合规检查

把 `project_rule.md` 的 10 条架构红线打包成一次性扫描器。用于把"纸面红线"变成"机械可执行"。

## 触发场景

- "检查架构违规"、"扫描硬编码"、"check architecture"
- 提交代码前的自检
- PR Review 时
- 怀疑某次修改破坏了分层边界
- `/verify` 交付自检后的第二道关卡

## 执行流程

### Step 1: 按信条运行 10 条红线扫描

一次 Bash 批量执行，路径相对项目根目录。

#### 配置即代码

```bash
# R1: 硬编码连接串
echo "=== R1: 硬编码连接串 ==="
grep -rnE "(mysql|postgres|redis)://[^\$\{]" backend/ scrapy/ 2>/dev/null | grep -vE "\.env\.example|README"

# R2: 明文 password
echo "=== R2: 明文 password ==="
grep -rnE 'password\s*=\s*"[^$]' backend/ scrapy/ 2>/dev/null | grep -vE "example|test_"
```

#### 爬取与存储分离

```bash
# R3: scrapy 禁止 import backend 内部
echo "=== R3: scrapy → backend 反向依赖 ==="
grep -rnE "^(from|import) (backend|app)\." scrapy/ 2>/dev/null

# R4: scrapy 禁止使用 SQLAlchemy Session（platform_core.models 仅作只读契约，禁止配 Session 写入）
echo "=== R4: scrapy 使用 SQLAlchemy ==="
grep -rnE "from sqlalchemy|SessionLocal|mysql_session|get_async_db" scrapy/ 2>/dev/null
```

#### 反爬是底线

```bash
# R5: DOWNLOAD_DELAY 必配
echo "=== R5: DOWNLOAD_DELAY ==="
grep -E "DOWNLOAD_DELAY" scrapy/settings.py 2>/dev/null || echo "❌ 缺失 DOWNLOAD_DELAY"

# R6: USER_AGENT 轮换
echo "=== R6: USER_AGENT 轮换 ==="
grep -rnE "USER_AGENT|UserAgentMiddleware" scrapy/ 2>/dev/null | head -5 || echo "❌ 缺失 USER_AGENT 配置"
```

#### 模型即契约

```bash
# R7: API 层禁止 import ORM 模型
echo "=== R7: API 层 import models ==="
grep -rnE "from.*\.models import" backend/app/api/ 2>/dev/null

# R8: ORM 模型禁止 import Pydantic schema
echo "=== R8: models 反向 import schemas ==="
grep -rnE "from.*\.schemas import" platform_core/models/ 2>/dev/null
```

#### 数据流向不可逆

```bash
# R9: 循环 import 检测
echo "=== R9: 循环 import ==="
python -c "import backend.app" 2>&1 | grep -iE "circular|cannot import name" || echo "✓ 无循环 import"
```

#### 日志即证据

```bash
# R10: service 公共方法入口必须有 logger（启发式扫描）
echo "=== R10: service 方法入口缺 logger ==="
for f in backend/services/*.py; do
  awk '/^(async )?def [a-z]/ {name=$0; getline; if ($0 !~ /logger\./) print FILENAME":"NR-1": "name}' "$f"
done 2>/dev/null
```

### Step 2: 汇总违规报告

按以下格式输出（禁止总结、必须贴具体 file:line）：

```
架构合规检查报告
==================
R1 硬编码连接串         backend/core/db.py:15        mysql://root:xxx@...
R3 scrapy→backend       scrapy/spiders/x.py:3        from backend.models ...
R5 缺失 DELAY           scrapy/settings.py:-         未配置 DOWNLOAD_DELAY
R10 service 缺 logger   backend/services/user.py:12  def create_user(...)

共 4 处违规，按优先级修复：R3 (架构级) > R1/R2 (安全) > R5/R6 (运行时) > R10 (可观测)
```

若无违规：

```
✓ 架构合规检查通过（10/10 项）
```

### Step 3: 按违规类型路由到修复 skill

| 违规 | 修复指引 |
|------|---------|
| R1 / R2 | `/config`：改为 `settings.MYSQL.HOST` 形式，敏感信息入 `.env` |
| R3 / R4 | `project_rule.md` "为什么爬虫不能直写主库"：改用 HTTP / MQ 交互 |
| R5 / R6 | `/new-spider`：拷贝反爬配置模板 |
| R7 / R8 | `/new-model`：用 converter 做 ORM↔Schema 的单向转换 |
| R9 | 找环路中间节点，引入抽象层或延迟 import |
| R10 | `/logging`：public 方法第一行 `logger.info("...")` |

## 输出约定

- 所有 grep 无结果 = 通过
- 有违规 = 在消息中列出具体 file:line，**禁止说"可能有违规"**
- 遵守 `answer_rule.md`：用工具验证，不要用嘴验证

## 相关 Rule / Skill

| 依赖 | 用途 |
|------|------|
| `project_rule.md` | 10 条红线定义的来源 |
| `/verify` | 交付自检的第一道关卡，本 skill 是第二道 |
| `/config` / `/logging` / `/new-spider` / `/new-model` | 违规的修复路径 |
