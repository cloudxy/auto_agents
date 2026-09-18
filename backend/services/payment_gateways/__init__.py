"""支付宝 / 微信支付网关接入（真实 SDK 签名与回调验签，非 HMAC 夹具）。

背景：`payment_provider.py` 原先的 `UnconfiguredOnlineProvider` 只是骨架，
`payment_notify_service.py` 用的是仓库自定义 HMAC 四要素比对（沙箱/CI 夹具，
不是支付宝/微信真实签名协议）。本包新增两条通道各自的真实签名/验签实现，
供 `payment_provider.py` 创建可支付链接/二维码、供新的外部回调端点验真。

- `alipay_gateway.py`：电脑网站支付（`alipay.trade.page.pay`），RSA2 签名/
  验签直接用项目已有的 `cryptography` 库实现——协议本身是公开文档化的稳定
  算法（排序拼接 key=value & 号连接 → RSA-SHA256 签名/验签），不额外引入
  `pycryptodome`/`pyOpenSSL` 这类与现有加密库重复的依赖。
- `wechat_gateway.py`：Native 支付（扫码），包一层微信支付官方生态圈里
  最常用的 `wechatpayv3` 第三方 SDK——APIv3 的证书自动下载/轮换 + AEAD 回调
  解密属于协议里最容易写错的部分，交给维护中的 SDK 而不是重新实现。

两条通道都通过 `secrets_schema.py` 从超管填写的 JSON 密钥包里解析结构化字段，
校验失败时给出人类可读的报错（缺哪个字段），而不是留到调用支付宝/微信时
才报一个不知所云的 SDK 异常。
"""
