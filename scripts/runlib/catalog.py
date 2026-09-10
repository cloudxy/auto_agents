from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    name: str
    module: str
    args: tuple[str, ...]
    port: int | None
    url: str | None = None


SERVICE_ORDER = ("backend", "spider", "admin", "official")

SERVICES: dict[str, Service] = {
    "backend": Service("backend", "scripts.runlib.backend", ("--no-reload",), 9111, "http://127.0.0.1:9111"),
    "spider": Service("spider", "scripts.runlib.spider", (), None),
    "admin": Service("admin", "scripts.runlib.frontend", ("--app", "admin", "--skip-install"), 9112, "http://127.0.0.1:9112"),
    "official": Service("official", "scripts.runlib.frontend", ("--app", "official", "--skip-install"), 9113, "http://127.0.0.1:9113"),
}

ALIASES = {
    "all": SERVICE_ORDER,
    "frontend": ("admin", "official"),
}


def resolve_targets(raw: list[str]) -> list[str]:
    names: list[str] = []
    for item in raw:
        if item in ALIASES:
            for name in ALIASES[item]:
                if name not in names:
                    names.append(name)
            continue
        if item not in SERVICES:
            raise ValueError(item)
        if item not in names:
            names.append(item)
    return names
