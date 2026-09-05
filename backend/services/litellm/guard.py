"""LiteLLM 镜像版本守卫（L1 供应链红线 · 纯函数零 IO）

背景：LiteLLM 1.82.7 / 1.82.8 为恶意版本（PyPI 侧 yanked、Docker Hub tag 已下架，
仍需防回归——下架≠永不重发，且自建镜像源/镜像缓存可能残留）。本模块把
「compose 解析 + 精确 pin + 黑名单断言」收口为纯函数：

- extract_litellm_image(compose_text)  compose YAML → litellm 服务 image 值
- image_tag(image)                    image 引用 → tag 段（含 digest 识别）
- check_version(tag)                  (ok, reason)：精确语义版本且不在黑名单
- check_compose(compose_text)          组合入口（守卫红测消费真实 docker-compose.yml）

消费方：backend/tests/test_litellm_version_guard.py（compose 变更时红）。
tag 判定口径：
- 精确语义版本 v?X.Y.Z 通过（v1.99.1 / 1.97.2）；
- latest / main-stable / main-latest / dev / X.Y 浮动前缀 / -dev.* 预发布 → 拒绝；
- 仅 digest pin（@sha256:...）→ 拒绝（无法对黑名单断言，版本信息缺失）。
"""
import re

import yaml

# 供应链红线：恶意版本黑名单（比较时剥离前导 v）
BLACKLISTED_VERSIONS = frozenset({"1.82.7", "1.82.8"})

# 精确语义版本 tag（v 前缀可选；显式排除 -dev.* 等预发布后缀）
_EXACT_TAG_RE = re.compile(r"^v?(\d+\.\d+\.\d+)$")
_DIGEST_RE = re.compile(r"@sha256:")

# 已知浮动 tag（LiteLLM Docker Hub 实际存在的指针性 tag）
_FLOATING_TAGS = frozenset({"latest", "main-stable", "main-latest", "dev", "stable"})


def extract_litellm_image(compose_text: str) -> str | None:
    """解析 compose 文本，返回 litellm 服务的 image 值。

    无 litellm 服务 / 无 image 键 / YAML 解析失败均返回 None（调用方按
    「未接入」处理；守卫红测对 None 判红——services 定义存在与否本身就是
    被守卫的契约）。用 yaml.safe_load 而非文本 grep：compose 是结构化 YAML，
    grep 会误伤注释与无关服务。
    """
    try:
        doc = yaml.safe_load(compose_text)
    except yaml.YAMLError:
        return None
    if not isinstance(doc, dict):
        return None
    services = doc.get("services")
    if not isinstance(services, dict):
        return None
    svc = services.get("litellm")
    if not isinstance(svc, dict):
        return None
    image = svc.get("image")
    return str(image) if image else None


def image_tag(image: str) -> str:
    """image 引用 → tag 段。

    litellm/litellm-database:v1.99.1 → v1.99.1
    litellm/litellm-database@sha256:abc → sha256:abc（digest pin 识别）
    litellm/litellm-database（无 tag）→ ""（隐式 latest）
    """
    if _DIGEST_RE.search(image):
        return "sha256:" + image.split("@sha256:", 1)[1]
    base = image.rsplit("/", 1)[-1]
    if ":" in base:
        return base.split(":", 1)[1]
    return ""


def check_version(tag: str) -> tuple[bool, str]:
    """断言 tag 为精确语义版本且不在黑名单。返回 (ok, reason)。

    reason 在 ok=False 时给出机械可读的拒绝理由（红测断言文本）。
    """
    if not tag:
        return False, "未 pin 版本（空 tag = 隐式 latest）"
    if tag.startswith("sha256:"):
        return False, "仅 digest pin 拒绝：无版本号，无法对恶意版本黑名单断言"
    if tag in _FLOATING_TAGS:
        return False, f"浮动 tag 禁用: {tag}"
    m = _EXACT_TAG_RE.match(tag)
    if not m:
        return False, f"非精确语义版本 tag（需 vX.Y.Z 形式）: {tag}"
    version = m.group(1)
    if version in BLACKLISTED_VERSIONS:
        return False, f"恶意版本黑名单命中: {version}（禁用版本 {sorted(BLACKLISTED_VERSIONS)}）"
    return True, f"精确版本 pin 通过: {version}"


def check_compose(compose_text: str) -> tuple[bool, str]:
    """守卫组合入口：compose 文本 → (ok, reason)。

    litellm 服务存在性 + image tag 精确 pin + 黑名单断言一次完成；
    测试直接传仓库根 docker-compose.yml 的文件内容。
    """
    image = extract_litellm_image(compose_text)
    if image is None:
        return False, "compose 中未定义 litellm 服务（或 image 键缺失/YAML 非法）"
    return check_version(image_tag(image))
