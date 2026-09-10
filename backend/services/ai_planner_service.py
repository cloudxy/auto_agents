"""AI 采集规划服务 —— 兼容门面（T6 service 解环后：纯静态 re-export）

历史路径 backend.services.ai_planner_service 被广泛引用（API 层 ai.py /
app lifespan 启动对账 / 存量单测的 import 与 patch 字符串路径），故保留本模块：

- 全部符号经静态 from-import re-export 自 backend.services.ai_planner 包
  （无 PEP 562 惰性 __getattr__、无文件末尾反向 import——二者曾是
  ai_planner_service ⇄ ai_planner 包 import 环的遮羞布，T6 已消除）；
- 本模块同时是「晚绑定测试缝」的宿主：初始化完成的末尾把自身模块对象
  注入 llm_common.seam（依赖注入）。包内子模块对可 patch 的可变依赖
  （settings / _spawn / SpiderService / _TOKEN_USAGE ...）经 seam() 调用期
  取值——mock.patch / monkeypatch.setattr 直接写入本模块 __dict__，
  对 seam() 的下一次取值即刻可见，与拆分前晚绑定语义完全一致；
- import 图恒无环：本门面 → ai_planner 包（单向）；包内模块 ⇏ 本门面
  （只经 llm_common.seam 叶子晚绑定）。

本模块不含任何业务实现，禁止在此新增逻辑。
"""
import sys as _sys

from backend.services import ai_planner as _package
from backend.services.ai_planner import *  # noqa: F401,F403 — 全量 re-export（含 __all__ 内私有名：存量 import/patch 目标）
from backend.services.llm_common.seam import bind as _bind_seam

__all__ = list(_package.__all__)

# 晚绑定测试缝装配：此后 seam() 返回本模块（包内业务代码的运行时取值点）
_bind_seam(_sys.modules[__name__])
