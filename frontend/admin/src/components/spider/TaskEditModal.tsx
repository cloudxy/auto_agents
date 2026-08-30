/**
 * TaskEditModal - 待执行任务编辑弹窗（仅 pending/queued 可改 params/priority）
 *
 * 后端 PATCH /spiders/tasks/{task_id} 校验：非 pending/queued 状态将拒绝；
 * 待执行任务改优先级会同步搬迁 Redis 队列。
 */
import React, { useEffect, useState } from 'react'
import { Modal, Form, Select, Input, Alert, message } from 'antd'
import { updateTask } from '../../services/spiders'
import type { Task } from './types'
import { apiErrorMessage, isFormValidateError } from '../../utils/errorMessage'

export interface TaskEditModalProps {
  visible: boolean
  task: Task | null
  onSubmitSuccess: (task: Task) => void
  onCancel: () => void
}

export const TaskEditModal: React.FC<TaskEditModalProps> = ({
  visible, task, onSubmitSuccess, onCancel,
}) => {
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    if (visible && task) {
      form.setFieldsValue({
        priority: task.priority || 'normal',
        params: task.params || '',
      })
    }
  }, [visible, task, form])

  const onSubmit = async () => {
    if (!task) return
    try {
      const values = await form.validateFields()
      const paramsStr = String(values.params || '').trim()
      if (paramsStr) {
        try {
          JSON.parse(paramsStr)
        } catch (error) {
          message.error('params 不是合法的 JSON')
          return
        }
      }
      setSubmitting(true)
      const updated = await updateTask(task.id, {
        params: paramsStr || undefined,
        priority: values.priority,
      })
      message.success(`任务 #${task.id} 已更新`)
      onCancel()
      onSubmitSuccess(updated)
    } catch (error) {
      if (isFormValidateError(error)) return
      message.error(apiErrorMessage(error, '更新失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title={`编辑待执行任务 #${task?.id ?? ''}`}
      open={visible}
      onOk={onSubmit}
      onCancel={onCancel}
      confirmLoading={submitting}
      okText="保存"
      cancelText="取消"
      destroyOnHidden
      width={560}
    >
      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        title="仅待执行（pending/queued）任务可编辑；运行中/已结束的任务后端将拒绝修改。"
      />
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item name="priority" label="优先级" tooltip="高优先级任务在同爬虫队列中优先被消费">
          <Select
            options={[
              { value: 'high', label: '高（优先执行）' },
              { value: 'normal', label: '普通' },
              { value: 'low', label: '低' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="params" label="任务参数（JSON）"
          tooltip='透传给爬虫的 JSON 字符串，如 {"urls": ["https://..."]}'
        >
          <Input.TextArea rows={6} placeholder='{"urls": ["https://..."]}' />
        </Form.Item>
      </Form>
    </Modal>
  )
}
