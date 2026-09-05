"""L1 版本守卫红测：compose litellm 镜像 tag 精确 pin + 恶意版本黑名单

核心用例 test_real_compose_pinned_and_not_blacklisted 直接读取仓库根
docker-compose.yml——任何人把 tag 改成 latest / 黑名单版本 / 摘掉 tag，
本文件即红（「compose 变更时红」的机械保证）。
"""
from pathlib import Path

import pytest

from backend.services.litellm.guard import (
    BLACKLISTED_VERSIONS,
    check_compose,
    check_version,
    extract_litellm_image,
    image_tag,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = PROJECT_ROOT / "docker-compose.yml"


class TestRealCompose:
    """真实 docker-compose.yml 守卫（防回归主阵地）"""

    def test_real_compose_pinned_and_not_blacklisted(self):
        ok, reason = check_compose(COMPOSE_PATH.read_text(encoding="utf-8"))
        assert ok, f"docker-compose.yml litellm 镜像守卫失败: {reason}"

    def test_real_compose_extract_image_shape(self):
        image = extract_litellm_image(COMPOSE_PATH.read_text(encoding="utf-8"))
        assert image is not None, "compose 缺 litellm 服务定义"
        assert image.startswith("litellm/litellm-database:"), f"镜像仓库漂移: {image}"


class TestCheckVersion:
    """tag 判定纯函数：精确 pin / 浮动 / 黑名单 / digest 四象限"""

    @pytest.mark.parametrize("tag", ["v1.99.1", "1.97.2", "v1.82.6", "1.100.0"])
    def test_exact_semver_accepted(self, tag):
        ok, _ = check_version(tag)
        assert ok, f"精确语义版本应通过: {tag}"

    @pytest.mark.parametrize("tag,frag", [
        ("", "空 tag"),
        ("latest", "浮动 tag"),
        ("main-stable", "浮动 tag"),
        ("main-latest", "浮动 tag"),
        ("dev", "浮动 tag"),
        ("v1.99", "非精确语义版本"),
        ("1.101.0-dev.2", "非精确语义版本"),
        ("v1.99.1-dev", "非精确语义版本"),
        ("sha256:e9842aba4cb4", "仅 digest pin"),
    ])
    def test_floating_or_digest_rejected(self, tag, frag):
        ok, reason = check_version(tag)
        assert not ok, f"应拒绝: {tag}"
        assert frag in reason

    @pytest.mark.parametrize("version", sorted(BLACKLISTED_VERSIONS))
    def test_blacklisted_rejected(self, version):
        for tag in (version, f"v{version}"):
            ok, reason = check_version(tag)
            assert not ok, f"恶意版本必须拒绝: {tag}"
            assert "黑名单" in reason

    def test_blacklist_contents_locked(self):
        """黑名单内容锁定（供应链红线：1.82.7 / 1.82.8 恶意版本）"""
        assert BLACKLISTED_VERSIONS == frozenset({"1.82.7", "1.82.8"})


class TestParsing:
    """compose 解析与 tag 提取纯函数"""

    def _compose(self, image: str | None) -> str:
        svc = 'services:\n  litellm:\n    image: "%s"\n' % (image or "")
        if image is None:
            svc = "services:\n  litellm:\n    profiles: [\"litellm\"]\n"
        return svc

    def test_extract_image(self):
        assert extract_litellm_image(self._compose("litellm/litellm-database:v1.99.1")) == \
            "litellm/litellm-database:v1.99.1"

    def test_extract_image_missing_service(self):
        assert extract_litellm_image("services:\n  backend:\n    image: x\n") is None

    def test_extract_image_invalid_yaml(self):
        assert extract_litellm_image("services: [unclosed") is None

    @pytest.mark.parametrize("image,expected", [
        ("litellm/litellm-database:v1.99.1", "v1.99.1"),
        ("litellm/litellm-database:1.97.2", "1.97.2"),
        ("litellm/litellm-database", ""),
        ("litellm/litellm-database:latest", "latest"),
        ("ghcr.io/berriai/litellm-database@sha256:abcd", "sha256:abcd"),
    ])
    def test_image_tag(self, image, expected):
        assert image_tag(image) == expected

    def test_check_compose_no_service_red(self):
        ok, reason = check_compose("services: {}")
        assert not ok and "未定义 litellm 服务" in reason

    def test_check_compose_blacklist_red(self):
        ok, reason = check_compose(self._compose("litellm/litellm-database:v1.82.8"))
        assert not ok and "黑名单" in reason
