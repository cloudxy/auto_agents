import React, { useState } from 'react'
import { Button, Form, Input, Modal, Select, message } from 'antd'

import { createTeam, listAssets } from '../../services/capabilities'
import { usePermission } from '../../hooks/usePermission'
import { apiErrorMessage } from '../../utils/errorMessage'
import TypeLeafTab from './TypeLeafTab'
import { CREATE_TEAM, TEAM_EMPTY } from './marketCopy'

const TEAM_TYPES = ['team', 'expert_team']

type Props = { onSubscribe: (name: string) => void }

const TeamLeafTab: React.FC<Props> = ({ onSubscribe }) => {
  const { isPlatformAdmin } = usePermission()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const [experts, setExperts] = useState<string[]>([])
  const [tick, setTick] = useState(0)

  const openForm = async () => {
    const data = await listAssets('expert').catch(() => ({ items: [] as { name: string }[] }))
    setExperts(data.items.map((i) => i.name))
    setOpen(true)
  }

  const onCreate = async () => {
    const values = await form.validateFields()
    try {
      await createTeam(values)
      message.success(`专家团「${values.name}」已创建`)
      setOpen(false)
      form.resetFields()
      setTick((n) => n + 1)
    } catch (e) {
      message.error(apiErrorMessage(e, '创建失败'))
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
        extra={isPlatformAdmin ? <Button type="primary" onClick={openForm}>{CREATE_TEAM}</Button> : null}
      />
      <Modal title={CREATE_TEAM} open={open} onOk={onCreate} onCancel={() => setOpen(false)} okText="创建">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="团队名" rules={[{ required: true }]}>
            <Input placeholder="如 review-squad" />
          </Form.Item>
          <Form.Item name="leader" label="团长智能体" rules={[{ required: true }]}>
            <Select options={experts.map((e) => ({ value: e, label: e }))} />
          </Form.Item>
          <Form.Item name="members" label="成员智能体">
            <Select mode="multiple" options={experts.map((e) => ({ value: e, label: e }))} />
          </Form.Item>
          <Form.Item name="workflow_md" label="协作流程">
            <Input.TextArea rows={3} placeholder="团长拆解 → 并行执行 → 汇总交付" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

export default TeamLeafTab
