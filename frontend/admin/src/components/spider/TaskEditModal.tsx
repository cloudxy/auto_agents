/**
 * TaskEditModal - 待执行任务编辑弹窗（仅 pending 可改 params/priority）
 *
 * U1-3（2026-08-31）：编辑复用与创建一致的注册表动态表单（原实现退化为手写
 * params JSON 文本域，与创建体验断崖）；表单未覆盖的扩展键以原 params 为
 * 基底 merge 保留。后端 PATCH /spiders/tasks/{id} 校验非 pending 拒绝。
 */
import React, { useEffect, useState } from 'react'
import { Modal, Form, Select, Alert, message } from 'antd'
import { updateTask } from '../../services/spiders'
import type { Task, SpiderRegistry } from './types'
import { renderParamFields, collectParams, paramsToFormValues, parseParamsJson } from './formUtils'
import { apiErrorMessage, isFormValidateError } from '../../utils/errorMessage'

export interface TaskEditModalProps {
  visible: boolean
  task: Task | null
  registry: SpiderRegistry
  onSubmitSuccess: (task: Task) => void
  onCancel: () => void
}

export const TaskEditModal: React.FC<TaskEditModalProps> = ({
  visible, task, registry, onSubmitSuccess, onCancel,
}) => {
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  // 任务爬虫对应的类型（决定动态表单字段集）
  const spiderMeta = task ? registry.spiders.find((s) => s.name === task.spider_name) : undefined
  const spiderType = spiderMeta?.type || 'web'
  const fields = registry.types.find((t) => t.type === spiderType)?.fields

  useEffect(() => {
    if (visible && task) {
      form.resetFields()
      const paramsObj = parseParamsJson(task.params)
      form.setFieldsValue({
        priority: task.priority || 'normal',
        ...paramsToFormValues(paramsObj, fields),
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, task])

  const onSubmit = async () => {
    if (!task) return
    try {
      const values = await form.validateFields()
      const collected = collectParams(values, fields)
      if (typeof collected === 'string') {
        message.error(collected)
        return
      }
      // 基底 merge：保留表单未覆盖的扩展键（store_to/render_js 等）
      const merged: Record<string, unknown> = {
        ...parseParamsJson(task.params),
        ...collected,
      }
      setSubmitting(true)
      const updated = await updateTask(task.id, {
        params: JSON.stringify(merged),
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
      title={`编辑待执行任务 #${task?.id ?? ''}（${spiderMeta?.title || task?.spider_name || ''}）`}
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
        message="仅待执行（pending）任务可编辑；运行中/已结束的任务后端将拒绝修改。"
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
        {renderParamFields(fields)}
      </Form>
    </Modal>
  )
}
