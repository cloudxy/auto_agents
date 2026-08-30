/**
 * TemplateModal - 收藏为任务模板弹窗
 */
import React, { useEffect, useState } from 'react'
import { Modal, Form, Input, Typography, message } from 'antd'
import { createTemplate } from '../../services/spiders'
import { PRIORITY_META } from './types'
import type { Task, SpiderMap } from './types'

const { Text } = Typography

export interface TemplateModalProps {
  visible: boolean
  task: Task | null
  spiderMap: SpiderMap
  onSubmitSuccess: () => void
  onCancel: () => void
}

export const TemplateModal: React.FC<TemplateModalProps> = ({
  visible, task, spiderMap, onSubmitSuccess, onCancel,
}) => {
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    if (visible && task) {
      form.resetFields()
      form.setFieldsValue({
        name: `${spiderMap[task.spider_name]?.title || task.spider_name} - 模板`,
        spider_name: task.spider_name,
        priority: task.priority || 'normal',
        params: task.params || '',
      })
    }
  }, [visible, task])

  const onSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      await createTemplate(values)
      message.success('已收藏为模板')
      onCancel()
      onSubmitSuccess()
    } catch (error: any) {
      if (error?.errorFields) return
      message.error(error?.response?.data?.message || error?.response?.data?.detail || '创建模板失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="收藏为任务模板"
      open={visible}
      onOk={onSubmit}
      onCancel={onCancel}
      confirmLoading={submitting}
      okText="保存模板"
      destroyOnHidden
      width={480}
    >
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="name"
          label="模板名称"
          rules={[
            { required: true, message: '请输入模板名称' },
            { max: 200, message: '名称不超过 200 字' },
          ]}
        >
          <Input placeholder="如：百度热搜每日采集" />
        </Form.Item>
        <Form.Item name="spider_name" label="爬虫" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="priority" label="优先级" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="params" label="参数（JSON）" hidden>
          <Input.TextArea />
        </Form.Item>
        {task && (
          <div style={{ padding: '8px 12px', background: '#f6ffed', borderRadius: 6, border: '1px solid #b7eb8f' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              将保存任务 #{task.id} 的配置：
              {spiderMap[task.spider_name]?.title || task.spider_name}，
              优先级：{PRIORITY_META[task.priority || 'normal']?.label || '普通'}
            </Text>
          </div>
        )}
      </Form>
    </Modal>
  )
}
