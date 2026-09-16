/**
 * T-11（附加 d / GWT-04.5 邻面）：示例维护弹窗——治理表格行操作。
 * 读源 = 公开详情 payload 的 examples（预览态豁免后 unlisted 也可读）；
 * 写源 = PATCH /capabilities/{t}/{n}/examples。上限 20 条 × 200 字（422 就近内联错误）。
 * 失败保留输入（弹窗不关、内容不清——最招投诉的反例，edge-states §7.1）。
 */
import React, { useEffect, useState } from 'react'
import { Alert, Button, Empty, Input, Modal, Space, Typography, message } from 'antd'

import {
  fetchPublicCapability, patchExamples, type AssetRow,
} from '../../services/capabilities'
import { apiErrorMessage } from '../../utils/errorMessage'

const { Text } = Typography

export const EXAMPLES_LIMIT = 20
export const EXAMPLE_MAX_CHARS = 200
export const EXAMPLES_EMPTY = '还没有示例。维护后，详情页会展示「帮你做的事」区块。'
export const EXAMPLES_LIMIT_COPY = `示例最多 ${EXAMPLES_LIMIT} 条，每条不超过 ${EXAMPLE_MAX_CHARS} 字`
export const EXAMPLES_ADD = '添加示例'
export const EXAMPLES_SAVING = '保存中…'

type Props = {
  open: boolean
  asset: AssetRow | null
  onClose: () => void
  onSaved: (row: AssetRow) => void
}

const ExamplesModal: React.FC<Props> = ({ open, asset, onClose, onSaved }) => {
  const [items, setItems] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [limitError, setLimitError] = useState(false)

  useEffect(() => {
    if (!open || !asset) return undefined
    let alive = true
    setLoading(true)
    setLimitError(false)
    fetchPublicCapability(asset.asset_type, asset.name)
      .then((detail) => { if (alive) setItems([...(detail.examples || [])]) })
      .catch(() => { if (alive) setItems([]) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [open, asset])

  const add = () => {
    if (items.length >= EXAMPLES_LIMIT) return
    setItems([...items, ''])
  }

  const update = (index: number, text: string) => {
    setItems(items.map((v, i) => (i === index ? text : v)))
  }

  const remove = (index: number) => {
    setItems(items.filter((_, i) => i !== index))
  }

  const submit = async () => {
    if (!asset || saving) return
    const trimmed = items.map((s) => s.trim()).filter((s) => s.length > 0)
    if (trimmed.length > EXAMPLES_LIMIT || trimmed.some((s) => s.length > EXAMPLE_MAX_CHARS)) {
      setLimitError(true)
      return
    }
    setLimitError(false)
    setSaving(true)
    try {
      const row = await patchExamples(asset.asset_type, asset.name, trimmed)
      message.success('示例已保存')
      onSaved(row)
      onClose()
    } catch (e) {
      // 422 超限 → 就近内联错误；其余失败 → toast（edge-states §7.3）
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 422) setLimitError(true)
      message.error(`操作失败：${apiErrorMessage(e, '请稍后重试')}`)
    } finally {
      setSaving(false)
    }
  }

  const atLimit = items.length >= EXAMPLES_LIMIT
  return (
    <Modal
      title={`维护示例 · ${asset?.name || ''}`}
      open={open}
      onCancel={() => { if (!saving) onClose() }}
      mask={{ closable: false }}
      destroyOnHidden
      footer={[
        <Button key="cancel" disabled={saving} onClick={onClose}>取消</Button>,
        <Button key="save" type="primary" loading={saving} onClick={() => { void submit() }}>
          {saving ? EXAMPLES_SAVING : '保存'}
        </Button>,
      ]}
    >
      {loading ? <Text type="secondary">正在读取现有示例…</Text> : (
        <>
          {items.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={EXAMPLES_EMPTY} />
          ) : null}
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {items.map((text, i) => (
              <div key={`${i}`} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <Input.TextArea
                  value={text}
                  rows={2}
                  maxLength={EXAMPLE_MAX_CHARS + 1}
                  aria-label={`示例 ${i + 1}`}
                  onChange={(e) => update(i, e.target.value)}
                  disabled={saving}
                />
                <Button disabled={saving} onClick={() => remove(i)} aria-label={`删除示例 ${i + 1}`}>
                  删除
                </Button>
              </div>
            ))}
          </Space>
          <div style={{ marginTop: 12 }}>
            <Button disabled={atLimit || saving} onClick={add}>{EXAMPLES_ADD}</Button>
            {atLimit ? <Text type="secondary" style={{ marginLeft: 8 }}>已达上限 {EXAMPLES_LIMIT} 条</Text> : null}
          </div>
          {limitError ? (
            <Alert type="error" role="alert" title={EXAMPLES_LIMIT_COPY} style={{ marginTop: 12 }} />
          ) : null}
        </>
      )}
    </Modal>
  )
}

export default ExamplesModal
