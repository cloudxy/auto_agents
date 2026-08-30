/**
 * TaskModal - 新增/编辑任务弹窗（动态表单 + 从模板创建）
 */
import React, { useState } from 'react'
import { Modal, Form, Radio, Select, Switch, message } from 'antd'
import type { SpiderRegistry, TaskTemplate, SpiderMap, Task } from './types'
import { renderParamFields, collectParams } from './formUtils'
import { runSpider } from '../../services/spiders'
import { apiErrorMessage, isFormValidateError } from '../../utils/errorMessage'

export interface TaskModalProps {
  visible: boolean
  registry: SpiderRegistry
  spiderMap: SpiderMap
  templates: TaskTemplate[]
  onSubmitSuccess: (task: Task) => void
  onCancel: () => void
}

export const TaskModal: React.FC<TaskModalProps> = ({
  visible, registry, spiderMap, templates,
  onSubmitSuccess, onCancel,
}) => {
  const [selectedType, setSelectedType] = useState<string>('web')
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  const currentType = registry.types.find((t) => t.type === selectedType)
  const spidersOfType = registry.spiders.filter((s) => s.type === selectedType)

  const open = (presetSpider?: string) => {
    form.resetFields()
    if (presetSpider && spiderMap[presetSpider]) {
      setSelectedType(spiderMap[presetSpider].type)
      form.setFieldsValue({ spider_name: presetSpider })
    } else {
      setSelectedType('web')
    }
  }

  // Expose open method via ref-like pattern: call open when visible changes
  React.useEffect(() => {
    if (visible) open()
  }, [visible])

  const onSubmitTask = async () => {
    try {
      const values = await form.validateFields()
      const collected = collectParams(values, currentType?.fields)
      if (typeof collected === 'string') {
        message.error(collected)
        return
      }
      if (values.incremental) {
        collected.incremental = true
      }
      setSubmitting(true)
      const task = await runSpider(values.spider_name, JSON.stringify(collected), values.priority || 'normal')
      message.success(`任务 #${task.id} 已提交，正在排队执行`)
      onCancel()
      onSubmitSuccess(task)
    } catch (error) {
      if (isFormValidateError(error)) return
      message.error(apiErrorMessage(error, '提交任务失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="新增采集任务"
      open={visible}
      onOk={onSubmitTask}
      onCancel={onCancel}
      confirmLoading={submitting}
      okText="提交任务"
      destroyOnHidden
      width={560}
    >
      <Form form={form} layout="vertical" preserve={false}>
        {templates.length > 0 && (
          <Form.Item label="从模板创建">
            <Select
              allowClear
              placeholder="选择模板快速填充（可选）"
              onChange={(templateId) => {
                const tpl = templates.find((t) => t.id === templateId)
                if (tpl) {
                  const spiderType = spiderMap[tpl.spider_name]?.type || 'web'
                  setSelectedType(spiderType)
                  form.setFieldsValue({
                    spider_name: tpl.spider_name,
                    priority: tpl.priority || 'normal',
                  })
                }
              }}
              options={templates.map((t) => ({
                label: `${t.name}（${spiderMap[t.spider_name]?.title || t.spider_name}）`,
                value: t.id,
              }))}
            />
          </Form.Item>
        )}

        <Form.Item label="任务类型" required>
          <Radio.Group
            value={selectedType}
            onChange={(e) => {
              setSelectedType(e.target.value)
              form.setFieldsValue({ spider_name: undefined })
            }}
            optionType="button"
            buttonStyle="solid"
            options={registry.types.map((t) => ({ label: t.label, value: t.type }))}
          />
        </Form.Item>

        <Form.Item
          name="spider_name"
          label="选择爬虫"
          rules={[{ required: true, message: '请选择爬虫' }]}
        >
          <Select
            placeholder={spidersOfType.length ? '选择该类型下的爬虫' : '该类型暂无可用爬虫'}
            options={spidersOfType.map((s) => ({
              label: `${s.title}（${s.name}）`,
              value: s.name,
            }))}
          />
        </Form.Item>

        <Form.Item name="priority" label="优先级" initialValue="normal" tooltip="高优先级任务在同爬虫队列中优先被消费">
          <Select
            options={[
              { value: 'high', label: '高（优先执行）' },
              { value: 'normal', label: '普通' },
              { value: 'low', label: '低' },
            ]}
          />
        </Form.Item>

        <Form.Item
          name="incremental"
          label="增量采集"
          valuePropName="checked"
          tooltip="开启后将跳过已采集的重复内容（基于内容指纹去重），适合定期重复运行的采集任务"
        >
          <Switch checkedChildren="开启" unCheckedChildren="关闭" />
        </Form.Item>

        {renderParamFields(currentType?.fields)}
      </Form>
    </Modal>
  )
}
