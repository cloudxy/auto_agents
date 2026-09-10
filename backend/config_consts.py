"""配置默认值唯一源（B3，工单 83）——热点内联默认值收口

问题：`settings.get(KEY, 默认值)` 的默认值散落各调用点（双写漂移）——
同一键在不同文件给不同默认值时行为分裂且不可发现。

约定：
- 本模块按「配置域」分组导出常量；调用点改为 `settings.get(KEY, CONST)`，
  新增键默认值一律先在此登记（评审可见、单点修改）
- 已在 config/default/*.yml 落有默认的键，此处值必须与 yml 一致
  （不一致即 bug——以 yml 为运行时真相，本常量是调用点兜底）

迁移进度：热点 Top-N 已收口（SKILLS.LIBRARY_ROOT ×9 / RELAY 开关 /
STALE_TASK_HOURS ×3 / USAGE_FLUSH_INTERVAL ×3 等）；剩余低频调用点渐进迁移，
新代码直接走本模块。
"""

# ---- 技能域 ----
SKILLS_LIBRARY_ROOT = "capability-library"
SKILLS_SCORING_ENABLED = False
SKILLS_PUBLIC_RATE_PER_MIN = 60

# ---- 能力市场源（与 config/default/power_market.yml 一致；D16 默认关）----
POWER_MARKET_ENABLED = False
POWER_MARKET_SRC_SYNC_LOCK_TTL = 900

# ---- new-api 墓碑（T-20：恒 false；运行时禁止 settings.get NEWAPI.*）----
NEWAPI_ENABLED = False

# ---- 平台网关值班产品规则（与 config/default/relay.yml 一致）----
RELAY_SCHEDULER_ENABLED = False
RELAY_PROBE_ENABLED = False
RELAY_INTERVAL_SECONDS = 300
RELAY_PROBE_INTERVAL_SECONDS = 86400
RELAY_LOCK_TTL_SECONDS = 120
RELAY_PROBE_LOCK_TTL_SECONDS = 21600
RELAY_PROBE_LOCK_RENEWAL_SECONDS = 600
RELAY_DEFAULT_WINDOW_QUOTA = 0
RELAY_DEFAULT_WINDOW_HOURS = 24
RELAY_DEFAULT_COOLDOWN_SECONDS = 3600

# ---- 任务与调度 ----
TASKS_STALE_TASK_HOURS = 6
SCHEDULER_TICK_SECONDS = 30
SCHEDULER_ENABLED = True
TASKS_CONSUMER_ENABLED = True

# ---- LLM ----
LLM_USAGE_FLUSH_INTERVAL = 60
LLM_MAX_ITERATIONS = 3
LLM_PROVIDER_BLOCK_PRIVATE_URL = False
LLM_DATA_PLANE = "litellm"  # T-20 完成态默认；providers 仅回滚窗

# ---- LiteLLM Proxy（与 config/default/litellm.yml 一致；MASTER_KEY 不落常量）----
LITELLM_BASE_URL = "http://127.0.0.1:4000"
LITELLM_TIMEOUT = 60

# ---- 存储与外部面 ----
STORAGE_DIR = "storage/exports"
STORAGE_REDIS_RESULT_TTL = 604800  # 7 天
EXTERNAL_API_KEYS: list = []
EXTERNAL_API_KEY_BINDINGS: list = []

# ---- Webhook / 探活 ----
WEBHOOK_SECRET_KEY = ""
WEBHOOK_MAX_CLOCK_SKEW = 300
PROXY_HEALTH_ENABLED = False
