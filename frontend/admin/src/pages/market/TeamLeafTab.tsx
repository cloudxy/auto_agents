import React, { useState } from 'react'
import { Button, Form, Input, Modal, Select, Space, Tag, message } from 'antd'

import {
  createTeam,
  getTeamDetail,
  listAssets,
  type AssetRow,
  type TeamDetail,
  type TeamMemberRef,
} from '../../services/capabilities'
import { usePermission } from '../../hooks/usePermission'
import { apiErrorMessage } from '../../utils/errorMessage'
import TypeLeafTab from './TypeLeafTab'
import { CREATE_TEAM, TEAM_AGENT_EMPTY, TEAM_EMPTY } from './marketCopy'

const TEAM_TYPES = ['team', 'expert_team']
const MEMBER_TYPE_LABEL: Record<string, string> = { expert: '专家', agent: '智能体' }
const MEMBER_SEP = '::'

/** T-37（FR-101）：成员引用编码 type::name（专家与智能体可同名，互不冲突） */
export const memberOptionValue = (type: string, name: string): string =>
  `${type}${MEMBER_SEP}${name}`

export const parseMemberOptionValue = (v: string): TeamMemberRef => {
  const sep = v.indexOf(MEMBER_SEP)
  if (sep < 0) return { type: 'expert', name: v }
  return {
    type: v.slice(0, sep) as TeamMemberRef['type'],
    name: v.slice(sep + MEMBER_SEP.length),
  }
}

/** 成员选择器数据源 = 专家 ∪ 智能体（GWT-101.3）；选项带类型标签；agent 空态句（101.4） */
export const buildMemberOptions = (experts: string[], agents: string[]) => [
  {
    label: '专家',
    options: experts.map((n) => ({
      value: memberOptionValue('expert', n),
      label: `${n}（专家）`,
    })),
  },
  {
    label: '智能体',
    options: agents.length
      ? agents.map((n) => ({
          value: memberOptionValue('agent', n),
          label: `${n}（智能体）`,
        }))
      : [{ value: `${'agent'}${MEMBER_SEP}__empty__`, label: TEAM_AGENT_EMPTY, disabled: true }],
  },
]

/** 旧团队 members 为名称字符串（按专家）；详情呈现统一成 typed 形态 */
export const normalizeMember = (m: TeamMemberRef | string): TeamMemberRef =>
  typeof m === 'string' ? { type: 'expert', name: m } : m

type Props = { onSubscribe: (name: string) => void }

const TeamLeafTab: React.FC<Props> = ({ onSubscribe }) => {
  const { isPlatformAdmin } = usePermission()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const [experts, setExperts] = useState<string[]>([])
  const [agents, setAgents] = useState<string[]>([])
  const [tick, setTick] = useState(0)
  const [teamDetail, setTeamDetail] = useState<TeamDetail | null>(null)

  const openForm = async () => {
    const [expertPack, agentPack] = await Promise.all([
      listAssets('expert').catch(() => ({ items: [] as { name: string }[] })),
      listAssets('agent').catch(() => ({ items: [] as { name: string }[] })),
    ])
    setExperts(expertPack.items.map((i) => i.name))
    setAgents(agentPack.items.map((i) => i.name))
    setOpen(true)
  }

  const onCreate = async () => {
    const values = await form.validateFields()
    try {
      await createTeam({
        name: values.name,
        leader: values.leader,
        members: (values.members || []).map(parseMemberOptionValue),
        workflow_md: values.workflow_md || '',
      })
      message.success(`专家团「${values.name}」已创建`)
      setOpen(false)
      form.resetFields()
      setTick((n) => n + 1)
    } catch (e) {
      message.error(apiErrorMessage(e, '创建失败'))
    }
  }

  const openDetail = async (row: AssetRow) => {
    try {
      setTeamDetail(await getTeamDetail(row.name))
    } catch (e) {
      message.error(apiErrorMessage(e, '详情加载失败'))
    }
  }

  return (
    <>
      <TypeLeafTab
        key={tick}
        types={TEAM_TYPES}
        leaf="专家团"
        emptyCopy={TEAM_EMPTY}
        onSubscribe={onSubscribe}
        onDetail={openDetail}
        extra={isPlatformAdmin ? <Button type="primary" onClick={openForm}>{CREATE_TEAM}</Button> : null}
      />
      <Modal title={CREATE_TEAM} open={open} onOk={onCreate} onCancel={() => setOpen(false)} okText="创建">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="团队名" rules={[{ required: true }]}>
            <Input placeholder="如 review-squad" />
          </Form.Item>
          <Form.Item name="leader" label="团长（专家）" rules={[{ required: true }]}>
            <Select options={experts.map((e) => ({ value: e, label: e }))} />
          </Form.Item>
          <Form.Item
            name="members"
            label="成员（专家 / 智能体）"
            extra={agents.length === 0 ? TEAM_AGENT_EMPTY : undefined}
          >
            <Select mode="multiple" options={buildMemberOptions(experts, agents)} />
          </Form.Item>
          <Form.Item name="workflow_md" label="协作流程">
            <Input.TextArea rows={3} placeholder="团长拆解 → 成员协同 → 汇总交付" />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={teamDetail ? `专家团 ${teamDetail.name}` : '专家团'}
        open={teamDetail !== null}
        footer={null}
        onCancel={() => setTeamDetail(null)}
      >
        {teamDetail ? (
          <div>
            <p><strong>团长</strong>：{teamDetail.leader}（专家）</p>
            <p><strong>成员</strong></p>
            <Space wrap>
              {teamDetail.members.map(normalizeMember).map((m) => (
                <Tag key={`${m.type}:${m.name}`}>
                  {MEMBER_TYPE_LABEL[m.type] || m.type} · {m.name}
                </Tag>
              ))}
            </Space>
            {teamDetail.workflow_md ? (
              <>
                <p style={{ marginTop: 12 }}><strong>协作流程</strong></p>
                <p style={{ whiteSpace: 'pre-wrap' }}>{teamDetail.workflow_md}</p>
              </>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  )
}

export default TeamLeafTab
