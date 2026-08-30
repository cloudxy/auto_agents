"""AI 采集规划服务 —— 兼容门面（期4 结构治理：实现拆分至 ai_planner/ 包）

历史路径 backend.services.ai_planner_service 被广泛引用（API 层 ai.py / app
lifespan 启动对账 / llm_provider_service 兜底透传 / 三个单测文件的 import 与
patch 字符串路径），故保留本模块为薄 shim（PEP 562 惰性命名空间）：

- 全部公开符号经 __getattr__ 惰性转发至 backend.services.ai_planner 包——
  旧 import 路径全部继续可用，且「先包后 shim / 先 shim 后包」双向入口均
  安全：模块级 star-import 写法在「先包后 shim」入口下（包 __init__ 途中
  子模块回引本门面）会因 __all__ 尚未定义而 ImportError，惰性转发不触碰
  部分初始化包的属性，天然规避循环导入；
- 存量单测 patch("backend.services.ai_planner_service.<name>") 的目标是本
  门面命名空间：mock.patch / monkeypatch 以 setattr 写入本模块 __dict__
  （实例属性查找优先于 PEP 562 __getattr__），包内模块经门面属性查找
  （_facade 模式，详见 ai_planner/__init__.py 模块 docstring）运行时读到
  的仍是 patch 后的值——晚绑定语义与原 star-import 完全一致；
- httpx.AsyncClient 的 patch 是全局模块属性替换（门面命名空间持有 httpx
  绑定即可被定位），天然兼容。

本模块不含任何业务实现，禁止在此新增逻辑。
"""
import backend.services.ai_planner as _package


def __getattr__(name: str):
    """PEP 562 惰性转发：未显式绑定于本模块的符号到实现包实时取值"""
    return getattr(_package, name)


def __dir__() -> list[str]:
    """dir() 委托实现包（补全 IDE / 交互式探索的符号可见性）"""
    return dir(_package)
