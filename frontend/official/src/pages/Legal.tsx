import React from 'react'
import { Typography } from 'antd'
import { useLocation } from 'react-router-dom'

const { Title, Paragraph } = Typography

const TERMS = {
  title: '服务条款',
  body: [
    '本平台提供多租户数据采集与大模型管理服务。注册即表示你同意按所选套餐使用配额内的并发、存储与 LLM token。',
    '你对提交的采集目标与产出数据负有合法合规责任；禁止采集法律法规禁止的内容。',
    '平台可在配额超限、欠费或滥用时限制或中止服务。',
  ],
}

const PRIVACY = {
  title: '隐私政策',
  body: [
    '我们处理的数据包括账号信息、租户成员、采集任务与结果、LLM 调用用量。采集结果可能含个人信息，由你作为数据控制者负责合法性基础。',
    '数据按租户隔离存储；外部 API 仅能通过你签发的 API Key 读取本租户结果。',
    '密钥以加密或哈希形式保存。你可申请导出或删除租户数据（受法定留存期约束）。',
  ],
}

const Legal: React.FC = () => {
  const isPrivacy = useLocation().pathname.includes('privacy')
  const doc = isPrivacy ? PRIVACY : TERMS
  return (
    <div style={{ maxWidth: 720, margin: '40px auto', padding: '0 24px 64px' }}>
      <Title level={2}>{doc.title}</Title>
      {doc.body.map((p) => (
        <Paragraph key={p}>{p}</Paragraph>
      ))}
    </div>
  )
}

export default Legal
