# 架构红线 + 核心代码边界扫描命令

按信条分组，一次 Bash 批量执行。路径相对项目根目录。

## 配置即代码

```bash
# R1: 硬编码连接串
echo "=== R1: 硬编码连接串 ==="
grep -rnE "(mysql|postgres|redis)://[^\$\{]" backend/ scrapy/ 2>/dev/null | grep -vE "\.env\.example|README"

# R2: 明文 password
echo "=== R2: 明文 password ==="
grep -rnE 'password\s*=\s*"[^$]' backend/ scrapy/ 2>/dev/null | grep -vE "example|test_"
```

## 爬取与存储分离

```bash
# R3: scrapy 禁止 import backend 内部
echo "=== R3: scrapy → backend 反向依赖 ==="
grep -rnE "^(from|import) (backend|app)\." scrapy/ 2>/dev/null

# R4: scrapy 禁止使用 SQLAlchemy Session（platform_core.models 仅作只读契约，禁止配 Session 写入）
echo "=== R4: scrapy 使用 SQLAlchemy ==="
grep -rnE "from sqlalchemy|SessionLocal|mysql_session|get_async_db" scrapy/ 2>/dev/null
```

## 反爬是底线

```bash
# R5: DOWNLOAD_DELAY 必配
echo "=== R5: DOWNLOAD_DELAY ==="
grep -E "DOWNLOAD_DELAY" scrapy/settings.py 2>/dev/null || echo "❌ 缺失 DOWNLOAD_DELAY"

# R6: USER_AGENT 轮换
echo "=== R6: USER_AGENT 轮换 ==="
grep -rnE "USER_AGENT|UserAgentMiddleware" scrapy/ 2>/dev/null | head -5 || echo "❌ 缺失 USER_AGENT 配置"
```

## 模型即契约

```bash
# R7: API 层禁止 import ORM 模型
echo "=== R7: API 层 import models ==="
grep -rnE "from.*\.models import" backend/app/api/ 2>/dev/null

# R8: ORM 模型禁止 import Pydantic schema
echo "=== R8: models 反向 import schemas ==="
grep -rnE "from.*\.schemas import" platform_core/models/ 2>/dev/null
```

## 数据流向不可逆

```bash
# R9: 循环 import 检测
echo "=== R9: 循环 import ==="
python -c "import backend.app" 2>&1 | grep -iE "circular|cannot import name" || echo "✓ 无循环 import"
```

## 日志即证据

```bash
# R10: service 公共方法入口必须有 logger（启发式扫描）
echo "=== R10: service 方法入口缺 logger ==="
for f in backend/services/*.py; do
  awk '/^(async )?def [a-z]/ {name=$0; getline; if ($0 !~ /logger\./) print FILENAME":"NR-1": "name}' "$f"
done 2>/dev/null
```

## 异步优先

```bash
# R11: async 上下文禁止同步 redis_client() 链式直调（阻塞事件循环，统一走 get_async_redis）
echo "=== R11: 同步 redis_client() 直调 ==="
grep -rnE 'redis_client\([^)]*\)\.' backend/ 2>/dev/null
```

## 核心代码边界（模块依赖方向）

```bash
# B1: platform_core 只依赖 config，禁止反向依赖 backend / scrapy
echo "=== B1: platform_core → backend/scrapy 反向依赖 ==="
grep -rnE "^(from|import) (backend|scrapy)" platform_core/ 2>/dev/null

# B2: backend 禁止直接 import scrapy（应通过 Redis 队列 / API 解耦）
echo "=== B2: backend → scrapy 直接依赖 ==="
grep -rnE "^(from|import) scrapy" backend/ 2>/dev/null

# B3: config 是最底层，禁止 import 任何业务模块
echo "=== B3: config → 业务模块反向依赖 ==="
grep -rnE "^(from|import) (backend|scrapy|platform_core)" config/ 2>/dev/null
```
