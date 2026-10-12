"""应用后台组件登记表回归（create_app 的 lifespan 按「模块路径 + 类名」字符串导入组件）。

字符串登记的代价是：类改名 / 挪模块不会在导入期报错，要等应用启动才炸。这里在测试期
把每一项解析一遍，并钉住关闭链与登记表一一对应。
"""
from __future__ import annotations

import inspect
from importlib import import_module

import pytest

import backend.app as app_pkg

SPECS = app_pkg._BACKGROUND_COMPONENTS


@pytest.mark.parametrize("spec", SPECS, ids=[s.name for s in SPECS])
def test_component_resolves_to_class_with_async_start_stop(spec):
    cls = getattr(import_module(spec.module), spec.cls)
    assert inspect.isclass(cls)
    for method in ("start", "stop"):
        assert inspect.iscoroutinefunction(getattr(cls, method)), f"{spec.cls}.{method} 须为 async"


def test_shutdown_order_covers_every_component_exactly_once():
    names = [s.name for s in SPECS]
    assert len(set(names)) == len(names)
    assert sorted(app_pkg._SHUTDOWN_ORDER) == sorted(names)
