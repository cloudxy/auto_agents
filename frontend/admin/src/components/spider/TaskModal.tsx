/**
 * TaskModal - 新增/编辑任务弹窗（动态表单 + 从模板创建 + 参数回填）
 *
 * U1-2（2026-08-31）：
 * - "重跑任务 / 手动运行调度 / 从模板创建"完整回填 params（含模板保存的参数）；
 * - 表单未覆盖的扩展键（store_to/render_js 等）以原 params 为基底 merge，不丢失。
 */
import React, { useState } from 'react'
import { Modal, Form, Radio, Select, Switch, message } from 'antd'
import type { SpiderRegistry, TaskTemplate, SpiderMap, Task } from './types'
import { renderParamFields, collectParams, paramsToFormValues, parseParamsJson } from './formUtils'
import { runSpider } from '../../services/spiders'
import { apiErrorMessage, isFormValidateError } from '../../utils/errorMessage'

/** 参数回填预设：来自任务行"运行"、调度"手动运行"或模板 */
export interface TaskPreset {
  spiderName?: string
  params?: string | null
  priority?: 'high' | 'normal' | 'low' | string | null
}

export interface TaskModalProps {
  visible: boolean
  registry: SpiderRegistry
  spiderMap: SpiderMap
  templates: TaskTemplate[]
  preset?: TaskPreset | null
  onSubmitSuccess: (task: Task) => void
  onCancel: () => void
}

export const TaskModal: React.FC<TaskModalProps> = ({
  visible, registry, spiderMap, templates, preset,
  onSubmitSuccess, onCancel,
}) => {
  const [selectedType, setSelectedType] = useState<string>('web')
  const [submitting, setSubmitting] = useState(false)
  // 基底参数（表单未覆盖的扩展键回填用）；用户手切类型/爬虫时清空防串键
  const [baseParams, setBaseParams] = useState<Record<string, unknown>>({})
  const [form] = Form.useForm()

  const currentType = registry.types.find((t) => t.type === selectedType)
  const spidersOfType = registry.spiders.filter((s) => s.type === selectedType)

  /** 回填入口：设置类型 + 爬虫 + 优先级 + 参数表单值 + 基底参数 */
  const applyPreset = (p: TaskPreset | null | undefined) => {
    setBaseParams({})
    if (!p?.spiderName || !spiderMap[p.spiderName]) {
      setSelectedType('web')
      return
    }
    const spiderType = spiderMap[p.spiderName].type
    setSelectedType(spiderType)
    const fields = registry.types.find((t) => t.type === spiderType)?.fields
    const paramsObj = parseParamsJson(p.params)
    setBaseParams(paramsObj)
    form.setFieldsValue({
      spider_name: p.spiderName,
      priority: (p.priority as string) || 'normal',
      ...paramsToFormValues(paramsObj, fields),
    })
  }

  // Expose open method via ref-like pattern: call open when visible changes
  React.useEffect(() => {
    if (visible) {
      form.resetFields()
      applyPreset(preset)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible])

  const onSubmitTask = async () => {
    try {
      const values = await form.validateFields()
      const collected = collectParams(values, currentType?.fields)
      if (typeof collected === 'string') {
        message.error(collected)
        return
      }
      // 基底 merge：保留表单未覆盖的扩展键（API 直建任务的 store_to/render_js 等）
      const merged: Record<string, unknown> = { ...baseParams, ...collected }
      if (values.incremental) {
        merged.incremental = true
      }
      setSubmitting(true)
      const task = await runSpider(
        values.spider_name,
        JSON.stringify(merged),
        values.priority || 'normal'
      )
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
      title={preset?.params ? '再次运行采集任务（参数已回填）' : '新增采集任务'}
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
              placeholder="选择模板快速填充（含已保存参数）"
              onChange={(templateId) => {
                const tpl = templates.find((t) => t.id === templateId)
                if (tpl) {
                  applyPreset({ spiderName: tpl.spider_name, params: tpl.params, priority: tpl.priority })
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
              setBaseParams({})
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
            onChange={() => setBaseParams({})}
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
