/**
 * T-25 订阅弹窗：选宿主订这一行。未声明名单 ≠ 已声明零项。禁止礼包句。
 * 四宿主位始终在。零项名单 = 全禁用，不是空弹窗。错误按 code 分支。
 */
import React, { useEffect, useState } from 'react'
import { Alert, Button, Modal, Radio, Space, Typography, message } from 'antd'

import {
  fetchPublicCapability,
  subscribeCapability,
  type PublicCapabilityCard,
} from '../services/capabilities'
import { apiErrorMessage } from '../utils/errorMessage'

const { Text } = Typography

export const HOSTS = ['grok', 'zcode', 'kimi', 'claude'] as const
export const HOST_LABELS: Record<string, string> = {
  grok: 'Grok', zcode: 'ZCode', kimi: 'Kimi', claude: 'Claude',
}
export const HOST_ZERO_NOTE = '该能力未声明支持任何宿主'

export const COPY_BY_CODE: Record<string, string> = {
  MARKET_READONLY_ROLE: '当前账号不能订阅，请联系企业管理员',
  MARKET_NEEDS_TENANT: '需要企业空间才能订阅',
  MARKET_COMING_SOON: '这是预告项，现在不能订阅。',
  MARKET_HOST_INCOMPAT: '该能力未声明支持该宿主',
  MARKET_NOT_FOUND: '没有这个能力，不能订阅。',
}

type ApiErr = { response?: { data?: { code?: string; message?: string } } }

const errorCode = (e: unknown): string | undefined => {
  if (typeof e !== 'object' || e === null) return undefined
  return (e as ApiErr).response?.data?.code
}

export const hostNote = (host: string, allowed: string[], declaredEmpty: boolean): string => {
  if (declaredEmpty) return HOST_ZERO_NOTE
  if (!allowed.includes(host)) return `该能力未声明支持 ${HOST_LABELS[host]}`
  return ''
}

export const successCopy = (host: string, created: boolean): string => {
  const label = HOST_LABELS[host] || host
  if (!created) return `已订阅到 ${label}，没有新增行。`
  return `已订阅到 ${label}`
}

export const formErrorFromCode = (code?: string, server?: string): string => {
  if (code === 'MARKET_HOST_INCOMPAT') return server || COPY_BY_CODE[code]
  if (code && COPY_BY_CODE[code]) return COPY_BY_CODE[code]
  return server || '订阅失败。检查网络后重试。'
}

interface Props {
  open: boolean
  assetType: string
  assetName: string
  onClose: () => void
  onSubscribed?: () => void
}

interface HostRadioProps {
  host: string | null
  allowed: string[]
  declaredEmpty: boolean
  loaded: boolean
  onHost: (value: string) => void
}

const HostRadioGroup: React.FC<HostRadioProps> = ({
  host, allowed, declaredEmpty, loaded, onHost,
}) => (
  <>
    {declaredEmpty ? (
      <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
        {HOST_ZERO_NOTE}
      </Text>
    ) : null}
    <Radio.Group
      value={host}
      onChange={(e) => onHost(e.target.value)}
      style={{ width: '100%' }}
    >
      <Space orientation="vertical">
        {HOSTS.map((h) => {
          const enabled = loaded && !declaredEmpty && allowed.includes(h)
          return (
            <Radio key={h} value={h} disabled={!enabled}>
              {HOST_LABELS[h]}
              {loaded && !enabled && !declaredEmpty ? (
                <Text type="secondary" style={{ marginLeft: 8 }}>
                  {hostNote(h, allowed, declaredEmpty)}
                </Text>
              ) : null}
            </Radio>
          )
        })}
      </Space>
    </Radio.Group>
  </>
)

const SubscribeModal: React.FC<Props> = ({
  open, assetType, assetName, onClose, onSubscribed,
}) => {
  const [card, setCard] = useState<PublicCapabilityCard | null>(null)
  const [host, setHost] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setHost(null)
    setFormError(null)
    setCard(null)
    fetchPublicCapability(assetType, assetName)
      .then(setCard)
      .catch((e) => {
        const code = errorCode(e)
        const server = (e as ApiErr).response?.data?.message
        setFormError(formErrorFromCode(code, server || apiErrorMessage(e, '加载失败')))
      })
  }, [open, assetType, assetName])

  const loaded = card !== null
  const allowed = loaded ? (card.hosts ?? HOSTS.slice()) : []
  const declaredEmpty = loaded && Array.isArray(card.hosts) && card.hosts.length === 0
  const canSubmit = Boolean(host) && allowed.includes(host || '') && !submitting && !declaredEmpty

  const submit = async () => {
    if (!host || !canSubmit) return
    setSubmitting(true)
    setFormError(null)
    try {
      const result = await subscribeCapability(assetType, assetName, host)
      message.success(successCopy(host, result.created))
      onSubscribed?.()
      onClose()
    } catch (e) {
      const code = errorCode(e)
      const server = (e as ApiErr).response?.data?.message
      setFormError(formErrorFromCode(code, server || apiErrorMessage(e, '订阅失败。检查网络后重试。')))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title={`订阅 ${assetName}`}
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      {formError ? <Alert type="error" showIcon title={formError} style={{ marginBottom: 12 }} /> : null}
      <HostRadioGroup
        host={host}
        allowed={allowed}
        declaredEmpty={declaredEmpty}
        loaded={loaded}
        onHost={setHost}
      />
      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button onClick={onClose}>取消</Button>
        <Button type="primary" disabled={!canSubmit} loading={submitting} onClick={submit}>
          {submitting ? '订阅中…' : `订阅到 ${host ? HOST_LABELS[host] : '宿主'}`}
        </Button>
      </div>
      <Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
        订阅不等于已在宿主运行
      </Text>
    </Modal>
  )
}

export default SubscribeModal
