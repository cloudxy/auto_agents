"""晚绑定命名空间缝（T6 service 解环的核心机制）

背景：ai_planner 包（期4 拆分）的子模块对「可被存量单测 patch 的可变依赖」
（settings / _spawn / SpiderService / _TOKEN_USAGE / _resolve_host_ips ...）
必须做调用期（晚绑定）属性读取——单测的 patch 目标是历史命名空间
backend.services.ai_planner_service（门面）。期4 用「子模块文件末尾
import 门面」实现晚绑定，形成 ai_planner_service ⇄ ai_planner 包的
import 环（R9 运行时检查检不出，属被语法手段掩盖的结构债）。

本模块是它的显式替代（依赖注入反转，不再有 import 环）：

- 门面 backend.services.ai_planner_service 是纯静态 re-export 模块（无
  PEP 562 惰性转发），在自身初始化完成的末尾调用 bind() 把模块对象注入本缝；
- 业务模块（ai_planner 包内子模块 / llm_common.runtime）需要晚绑定读取时经
  seam() 取命名空间，禁止 import 门面——import 图严格无环：
  业务模块 → llm_common.seam（叶子）← 门面（单向注入）；
- patch 门面属性（mock.patch / monkeypatch.setattr 直接写入门面模块 __dict__）
  对 seam() 的下一次取值即刻可见，与拆分前的晚绑定语义完全一致。

未装配（门面从未被 import）时 seam() 抛 RuntimeError 而非静默错值——
backend.app 的路由聚合（api/v1/ai.py）与一切 patch 门面路径的单测都会先装载
门面，正常装配流程不可能触达该分支。
"""
from types import ModuleType
from typing import Optional

_seam_ns: Optional[ModuleType] = None


def bind(namespace: ModuleType) -> None:
    """注入晚绑定命名空间（门面初始化完成时调用；后绑覆盖前绑，幂等可重复）"""
    global _seam_ns
    _seam_ns = namespace


def seam() -> ModuleType:
    """取晚绑定命名空间（调用期解析：对门面属性的 patch 即刻可见）"""
    if _seam_ns is None:
        raise RuntimeError(
            "llm_common.seam 未装配：需先 import backend.services.ai_planner_service"
            "（backend.app 路由聚合默认装载），或显式调用 llm_common.seam.bind()"
        )
    return _seam_ns
