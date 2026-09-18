/**
 * T-15（FR-02 / QA-2 / QA-9，状态契约 = edge-states §7.7 六态）：
 * 打开弹窗即发 dry_run=true 取计数（加载态）→ 零失源空态 / 确认句「将下线
 * {n} 个无磁盘来源的资产」+ 预览清单 → 确认后不带 dry_run 执行 → toast 对账
 * 三元组。取消零写入；失败可重试不自动重试；执行中禁 ×/取消/Esc。
 */
import React, { useEffect, useState } from 'react'
import { Alert, Button, Modal, Skeleton, Tag, Typography, message } from 'antd'

import { pruneMissingAssets, type PruneMissingResult } from '../../services/capabilities'
import { apiErrorMessage } from '../../utils/errorMessage'
import { typeLabelOf } from './shelfCopy'

const { Text } = Typography

export const PRUNE_TITLE = '清理失源资产'
export const PRUNE_CHECKING = '正在核对失源资产…'
export const PRUNE_ZERO = '当前无失源资产'
export const PRUNE_ZERO_HINT = '存活资产与 .agents 磁盘内容一致，无需清理'
export const PRUNE_CONFIRM = '确认清理'
export const PRUNE_RUNNING = '清理中…'
export const PRUNE_CANCEL_TOAST = '已取消，未下线任何资产'
export const PRUNE_CLOSE = '关闭'
const PREVIEW_LIST_MAX = 20

const confirmCopy = (n: number): string => `将下线 ${n.toLocaleString('zh-Hans')} 个无磁盘来源的资产`
const doneCopy = (n: number, liveTotal: number, diskTotal: number): string =>
  `清理完成：下线 ${n.toLocaleString('zh-Hans')} 个 · 存活 ${liveTotal.toLocaleString('zh-Hans')} · 磁盘 ${diskTotal.toLocaleString('zh-Hans')}`
const failCopy = (reason: string): string => `清理失败：${reason}。请重试。`

type Phase = 'loading' | 'zero' | 'ready' | 'executing' | 'error'

type Props = {
  open: boolean
  onClose: () => void
  onPruned: (result: PruneMissingResult) => void
}

const PruneConfirmModal: React.FC<Props> = ({ open, onClose, onPruned }) => {
  const [phase, setPhase] = useState<Phase>('loading')
  const [preview, setPreview] = useState<PruneMissingResult | null>(null)
  const [errorText, setErrorText] = useState('')
  const [failedKind, setFailedKind] = useState<'dry' | 'execute' | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!open) return
    setPhase('loading')
    setPreview(null)
    setErrorText('')
    setFailedKind(null)
    setExpanded(false)
    // 打开即 dry_run（QA-9）：取同构预览不落库
    pruneMissingAssets(true)
      .then((result) => {
        setPreview(result)
        setPhase(result.pruned.length === 0 ? 'zero' : 'ready')
      })
      .catch((e) => {
        setFailedKind('dry')
        setErrorText(apiErrorMessage(e, '请稍后重试'))
        setPhase('error')
      })
  }, [open])

  const execute = async () => {
    if (phase !== 'ready') return
    setPhase('executing')
    try {
      const result = await pruneMissingAssets(false)
      message.success(doneCopy(result.pruned.length, result.live_total, result.disk_total))
      onPruned(result)
      onClose()
    } catch (e) {
      setFailedKind('execute')
      setErrorText(apiErrorMessage(e, '请稍后重试'))
      setPhase('error')
    }
  }

  const retry = () => {
    if (failedKind === 'dry') {
      setPhase('loading')
      pruneMissingAssets(true)
        .then((result) => {
          setPreview(result)
          setErrorText('')
          setFailedKind(null)
          setPhase(result.pruned.length === 0 ? 'zero' : 'ready')
        })
        .catch((e) => { setErrorText(apiErrorMessage(e, '请稍后重试')) })
    } else {
      setPhase('ready')
      void execute()
    }
  }

  const cancel = () => {
    if (phase === 'executing') return
    message.info(PRUNE_CANCEL_TOAST)
    onClose()
  }

  const n = preview?.pruned.length ?? 0
  const executing = phase === 'executing'
  const zero = phase === 'zero'

  return (
    <Modal
      title={PRUNE_TITLE}
      open={open}
      onCancel={cancel}
      closable={!executing}
      keyboard={!executing}
      mask={{ closable: false }}
      destroyOnHidden
      footer={
        phase === 'error' && failedKind ? [
          <Button key="cancel" onClick={cancel}>取消</Button>,
          <Button key="retry" type="primary" onClick={retry}>重试</Button>,
        ] : zero ? [
          <Button key="close" type="primary" onClick={onClose}>{PRUNE_CLOSE}</Button>,
        ] : [
          <Button key="cancel" disabled={executing} onClick={cancel}>取消</Button>,
          <Button
            key="confirm"
            type="primary"
            danger
            disabled={phase !== 'ready'}
            loading={executing}
            onClick={() => { void execute() }}
          >
            {executing ? PRUNE_RUNNING : PRUNE_CONFIRM}
          </Button>,
        ]
      }
    >
      {phase === 'loading' ? (
        <div aria-live="polite" data-testid="prune-checking">
          <Skeleton active paragraph={{ rows: 1 }} />
          <Text type="secondary">{PRUNE_CHECKING}</Text>
        </div>
      ) : null}
      {zero ? (
        <div data-testid="prune-zero">
          <p>{PRUNE_ZERO}</p>
          <Text type="secondary">{PRUNE_ZERO_HINT}</Text>
        </div>
      ) : null}
      {(phase === 'ready' || phase === 'executing') && preview ? (
        <div data-testid="prune-ready">
          <p role="alert">{confirmCopy(n)}</p>
          <div className="prune-preview-list">
            {(expanded ? preview.pruned : preview.pruned.slice(0, PREVIEW_LIST_MAX)).map((p) => (
              <div key={`${p.asset_type}-${p.name}`} className="prune-preview-row">
                <Tag>{typeLabelOf(p.asset_type)}</Tag>
                <Text code>{p.name}</Text>
              </div>
            ))}
            {preview.pruned.length > PREVIEW_LIST_MAX ? (
              <Button type="link" onClick={() => setExpanded((v) => !v)}>
                {expanded ? '收起' : `展开全部 ${preview.pruned.length}`}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
      {phase === 'error' ? (
        <div data-testid="prune-error">
          <Alert type="error" showIcon title={failCopy(errorText)} role="alert" />
        </div>
      ) : null}
    </Modal>
  )
}

export default PruneConfirmModal
