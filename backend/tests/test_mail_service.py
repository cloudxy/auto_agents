"""邮件发送（决策 D25：对外联系与提醒走邮箱）

- 未启用 SMTP（开发 / 测试默认）：写进本地发件箱目录，流程照常走通
- 启用：经 SMTP 发出（SSL / STARTTLS 按配置）；发送失败返回 False、不抛到业务主路径
- 公开联系接口带出联系邮箱与响应时效
"""
from __future__ import annotations

import asyncio
from email import message_from_bytes
from email.header import decode_header, make_header

import pytest


def _set(monkeypatch, **values):
    from config import settings

    originals = {k: settings.get(k) for k in values}
    for k, v in values.items():
        settings.set(k, v)
    return originals


@pytest.fixture
def mail_cfg(tmp_path):
    from config import settings

    keys = ("MAIL.ENABLED", "MAIL.OUTBOX_DIR", "MAIL.HOST", "MAIL.PORT", "MAIL.USE_SSL", "MAIL.FROM")
    originals = {k: settings.get(k) for k in keys}
    settings.set("MAIL.ENABLED", False)
    settings.set("MAIL.OUTBOX_DIR", str(tmp_path / "outbox"))
    settings.set("MAIL.FROM", "AutoAgents <no-reply@example.com>")
    yield tmp_path / "outbox"
    for k, v in originals.items():
        settings.set(k, v)


def test_disabled_writes_to_outbox(mail_cfg):
    from backend.services.mail_service import send_mail

    assert asyncio.run(send_mail("owner@acme.cn", "企业档即将到期", "还有 3 天到期。")) is True
    files = list(mail_cfg.glob("*.eml"))
    assert len(files) == 1
    msg = message_from_bytes(files[0].read_bytes())
    assert msg["To"] == "owner@acme.cn"
    assert str(make_header(decode_header(msg["Subject"]))) == "企业档即将到期"
    assert "还有 3 天到期。" in msg.get_payload(decode=True).decode("utf-8")


def test_enabled_sends_via_smtp(mail_cfg, monkeypatch):
    import backend.services.mail_service as svc
    from config import settings

    sent = []

    class _SMTP:
        def __init__(self, host, port, timeout=None, **_kw):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, password):
            sent.append(("login", user))

        def send_message(self, msg):
            sent.append(("send", msg["To"]))

    monkeypatch.setattr(svc.smtplib, "SMTP_SSL", _SMTP)
    settings.set("MAIL.ENABLED", True)
    settings.set("MAIL.HOST", "smtp.example.com")
    settings.set("MAIL.PORT", 465)
    settings.set("MAIL.USE_SSL", True)
    monkeypatch.setenv("MAIL_USERNAME", "robot@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "secret")
    assert asyncio.run(svc.send_mail("a@b.cn", "主题", "正文")) is True
    assert ("connect", "smtp.example.com", 465) in sent and ("send", "a@b.cn") in sent
    assert ("login", "robot@example.com") in sent
    assert not list(mail_cfg.glob("*.eml"))


def test_smtp_failure_returns_false(mail_cfg, monkeypatch):
    import backend.services.mail_service as svc
    from config import settings

    class _Boom:
        def __init__(self, *a, **k):
            raise OSError("connection refused")

    monkeypatch.setattr(svc.smtplib, "SMTP_SSL", _Boom)
    settings.set("MAIL.ENABLED", True)
    settings.set("MAIL.HOST", "smtp.example.com")
    settings.set("MAIL.USE_SSL", True)
    assert asyncio.run(svc.send_mail("a@b.cn", "主题", "正文")) is False


def test_public_contact_exposes_email_and_sla(client, monkeypatch):
    from config import settings

    originals = {k: settings.get(k) for k in ("OPS.CONTACT_EMAIL", "OPS.CONTACT_SLA")}
    settings.set("OPS.CONTACT_EMAIL", "sales@example.com")
    settings.set("OPS.CONTACT_SLA", "工作日 24 小时内回复")
    try:
        data = client.get("/api/v1/public/ops-contact").json()["data"]
    finally:
        for k, v in originals.items():
            settings.set(k, v)
    assert data["contact_email"] == "sales@example.com"
    assert data["contact_sla"] == "工作日 24 小时内回复"
    assert "duty_contact" in data


def test_pytest_never_sends_real_mail():
    """本机 config/local/.env 可能启用了真实 SMTP：测试进程一律不发真信、不写仓库发件箱

    注册、到期巡检等用例会走真实发信路径，收件人是 boss@acme-d21.cn 之类的假地址——
    不拦就会用开发者的邮箱往外发信。需要测 SMTP 分支的用例自己打开并桩掉 smtplib。
    """
    from pathlib import Path

    from config import settings

    assert not settings.get("MAIL.ENABLED")
    outbox = Path(str(settings.get("MAIL.OUTBOX_DIR")))
    repo_runtime = Path(__file__).resolve().parents[2] / "runtime"
    assert outbox.is_absolute() and repo_runtime not in outbox.parents
