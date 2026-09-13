/**
 * 渠道组用法区（T-10 / GWT-60.1）：Base URL + 三步用法。
 * 页面空态与签发成功弹窗同一屏复用（edge-states 渠道组屏：用法区在空态仍渲染）。
 *
 * Base URL 来自 PUBLIC_BASE_URL 系配置：REACT_APP_RELAY_PUBLIC_BASE_URL，
 * 缺省对齐 config/default/litellm.yml 的 LITELLM.BASE_URL 本机默认——
 * 禁止写死出站拉数地址、禁止出现平台网关钥匙（master）。
 */
import React from 'react'
import { Typography, message } from 'antd'

const { Text, Paragraph } = Typography

export const RELAY_BASE_URL = (process.env.REACT_APP_RELAY_PUBLIC_BASE_URL || 'http://127.0.0.1:4000')
  .replace(/\/+$/, '')

/** 三步固定文案（spec GWT-60.1 / edge-states 渠道组屏，不 paraphrase） */
export const RELAY_USAGE_STEPS = ['复制 Base URL', '粘贴令牌', '发一条请求']

const RelayUsage: React.FC = () => (
  <div data-testid="relay-usage">
    <Paragraph style={{ marginBottom: 8 }}>
      Base URL：
      <Text
        code
        copyable={{
          onCopy: () => message.success('已复制 Base URL'),
        }}
        style={{ wordBreak: 'break-all' }}
        data-testid="relay-base-url"
      >
        {RELAY_BASE_URL}
      </Text>
    </Paragraph>
    <Paragraph style={{ marginBottom: 0 }} data-testid="relay-usage-steps">
      三步用法：{RELAY_USAGE_STEPS.join(' → ')}
    </Paragraph>
  </div>
)

export default RelayUsage
