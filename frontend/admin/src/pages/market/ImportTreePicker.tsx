/**
 * T-12（FR-07 / AD-4a / NFR-08）：目录导入向导（webkitdirectory 整树上传）。
 * 三步：选择目录（本地回显 + >500 前端预检）→ 导入预览（类型分组 + 新建/更新
 * 标注 + 跳过清单含非法路径）→ 结果（汇总 + 逐条失败原因）。
 * 两段式无状态：取消 = 不发 confirm，零写入 toast（GWT-07.2）；确认重传同一棵树。
 * 上传形态：form.append('files', f, f.webkitRelativePath || f.name)（服务端按树判型）。
 * 浏览器不支持 webkitdirectory：目录按钮不渲染，[使用服务器路径] 走父层高级项（能力不缺失）。
 */
import React, { useRef, useState } from 'react'
import {
  Alert, Button, Empty, Modal, Progress, Skeleton, Space, Steps, Tag, Typography, message,
} from 'antd'
import type { AxiosProgressEvent } from 'axios'

import {
  confirmTreeImport, previewTreeImport,
  type TreeConfirmResult, type TreeImportAsset, type TreePreviewResult,
} from '../../services/capabilities'
import { apiErrorMessage } from '../../utils/errorMessage'
import {
  IMPORT_CANCEL, IMPORT_FINISH, IMPORT_NETWORK_FAIL, IMPORT_PARSE_RETRY,
  IMPORT_PARSING, IMPORT_RESELECT, IMPORT_RETRY, IMPORT_STEP_RESULT,
  IMPORT_STEP_SELECT, IMPORT_TYPE_LABELS, uploadingCopy,
} from './importWizardCopy'

const { Text } = Typography

const MAX_TREE_FILES = 500

export const TREE_CHOOSE_HINT = '选择包含技能、命令、智能体或插件的目录，类型自动识别。'
export const TREE_OVER_LIMIT = '单次最多导入 500 个文件，请改用服务器路径导入'
export const TREE_EMPTY_TITLE = '未识别到可导入资产'
export const TREE_EMPTY_HINT = '目录里没有 SKILL.md、plugin.json、agents/ 或 commands/ 可识别的结构'
export const TREE_CANCEL_TOAST = '已取消，未写入任何资产'
export const TREE_USE_SERVER = '使用服务器路径'
export const TREE_SELECT_DIR = '选择目录'
export const TREE_START_PARSE = '开始解析'
export const USE_SERVER_PATH = '使用服务器路径'

const typeLabel = (t: string): string => IMPORT_TYPE_LABELS[t] || t
const relPathOf = (f: File): string =>
  (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
const dirNameOf = (files: File[]): string => (relPathOf(files[0]).split('/')[0] || '')

const hasResponse = (e: unknown): boolean => (
  typeof e === 'object' && e !== null
  && 'response' in e && (e as { response?: unknown }).response != null
)

const isOverLimit422 = (e: unknown): boolean => (
  (e as { response?: { status?: number } })?.response?.status === 422
)

type Failure = { kind: 'network' | 'parse' | 'limit'; text: string }

type Props = {
  open: boolean
  /** 取消/关闭（imported = 本轮已有成功导入项） */
  onCancel: (imported: boolean) => void
  /** 完成：关闭 + 刷新目录 */
  onFinished: () => void
  /** [使用服务器路径]：切回父向导高级项并聚焦 */
  onUseServerPath?: () => void
}

const actionTag = (a: 'create' | 'update'): React.ReactNode => (
  a === 'create' ? <Tag color="success">新建</Tag> : <Tag color="processing">更新</Tag>
)

const assetRow = (asset: TreeImportAsset, depth = 0): React.ReactNode => (
  <div
    key={`${depth}-${asset.asset_type}-${asset.name}`}
    style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', marginLeft: depth * 16 }}
  >
    <Tag>{typeLabel(asset.asset_type)}</Tag>
    <Text code>{asset.name}</Text>
    {actionTag(asset.action)}
    {asset.origin_path ? (
      <Text type="secondary" style={{ fontSize: 12 }}>{asset.origin_path}</Text>
    ) : null}
    {(asset.bundled || []).map((child) => assetRow(child, depth + 1))}
  </div>
)

const ImportTreePicker: React.FC<Props> = ({ open, onCancel, onFinished, onUseServerPath }) => {
  const [phase, setPhase] = useState<'select' | 'preview' | 'result'>('select')
  const [files, setFiles] = useState<File[]>([])
  const [pending, setPending] = useState(false)
  const [percent, setPercent] = useState<number | null>(null)
  const [parsing, setParsing] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)
  const [preview, setPreview] = useState<TreePreviewResult | null>(null)
  const [result, setResult] = useState<TreeConfirmResult | null>(null)
  const [expanded, setExpanded] = useState(false)
  const dirInput = useRef<HTMLInputElement | null>(null)

  const picked = files.length > 0
  const overLimit = files.length > MAX_TREE_FILES
  const imported = Boolean(result && result.created + result.updated > 0)

  const reselect = () => {
    setPhase('select')
    setFiles([])
    setFailure(null)
    setPreview(null)
    setResult(null)
    setExpanded(false)
    setPercent(null)
    setParsing(false)
  }

  const onPickDir = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFiles(Array.from(e.target.files || []))
    setFailure(null)
    e.target.value = ''
  }

  const trackUpload = (event: AxiosProgressEvent) => {
    if (!event.total) return
    const p = Math.min(100, Math.round((event.loaded / event.total) * 100))
    setPercent(p)
    if (p >= 100) setParsing(true)
  }

  const runPreview = async () => {
    if (!picked || overLimit || pending) return
    setPending(true)
    setFailure(null)
    setPercent(null)
    setParsing(false)
    try {
      const data = await previewTreeImport(files, trackUpload)
      setPreview(data)
      setPhase('preview')
    } catch (e) {
      if (isOverLimit422(e)) {
        setFailure({ kind: 'limit', text: TREE_OVER_LIMIT })
      } else if (hasResponse(e)) {
        setFailure({ kind: 'parse', text: `解析失败。${apiErrorMessage(e, IMPORT_PARSE_RETRY)}。` })
      } else {
        setFailure({ kind: 'network', text: IMPORT_NETWORK_FAIL })
      }
    } finally {
      setPending(false)
      setPercent(null)
      setParsing(false)
    }
  }

  const runConfirm = async () => {
    if (!preview || pending) return
    setPending(true)
    setFailure(null)
    try {
      const data = await confirmTreeImport(files, trackUpload)
      setResult(data)
      setPhase('result')
    } catch (e) {
      if (hasResponse(e)) {
        setFailure({ kind: 'parse', text: `解析失败。${apiErrorMessage(e, IMPORT_PARSE_RETRY)}。` })
      } else {
        setFailure({ kind: 'network', text: IMPORT_NETWORK_FAIL })
      }
    } finally {
      setPending(false)
      setPercent(null)
      setParsing(false)
    }
  }

  const cancel = () => {
    if (pending) return
    // 预览步骤取消 = 不发 confirm（两段式无状态，零写入）
    if (phase === 'preview') message.info(TREE_CANCEL_TOAST)
    onCancel(imported)
  }

  const selectBody = (
    <>
      {failure ? (
        <Alert
          type="error"
          showIcon
          title={failure.kind === 'limit' ? TREE_OVER_LIMIT : failure.text}
          description={failure.kind === 'limit' ? `当前 ${files.length} 个` : undefined}
          style={{ marginBottom: 12 }}
          action={failure.kind === 'network' ? (
            <Button size="small" disabled={pending} onClick={() => { void runPreview() }}>
              {IMPORT_RETRY}
            </Button>
          ) : failure.kind === 'limit' ? (
            onUseServerPath ? (
              <Button size="small" onClick={onUseServerPath}>{TREE_USE_SERVER}</Button>
            ) : undefined
          ) : (
            <Button size="small" onClick={reselect}>{IMPORT_RESELECT}</Button>
          )}
        />
      ) : null}
      {!picked && !pending ? (
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>{TREE_CHOOSE_HINT}</Text>
      ) : null}
      <input
        ref={dirInput}
        type="file"
        multiple
        style={{ display: 'none' }}
        onChange={onPickDir}
        data-testid="tree-dir-input"
      />
      {picked ? (
        <Space wrap>
          <Text>已选择：{dirNameOf(files)} · {files.length} 个文件</Text>
          <Button onClick={() => dirInput.current?.click()}>{IMPORT_RESELECT}</Button>
          {overLimit ? <Text type="danger">当前 {files.length} 个</Text> : null}
        </Space>
      ) : (
        <Button type="primary" onClick={() => dirInput.current?.click()}>{TREE_SELECT_DIR}</Button>
      )}
      {pending ? (
        <div style={{ marginTop: 16 }} aria-live="polite">
          <Text>{parsing || (percent !== null && percent >= 100) ? IMPORT_PARSING : (percent !== null ? uploadingCopy(percent) : '上传中…')}</Text>
          {percent !== null ? <Progress percent={percent} size="small" /> : null}
          {parsing ? <Skeleton active paragraph={{ rows: 3 }} style={{ marginTop: 8 }} /> : null}
        </div>
      ) : null}
    </>
  )

  const groups = preview
    ? (['skill', 'plugin', 'command', 'agent'] as const)
      .map((t) => ({ type: t, count: preview.counts[t] }))
      .filter((g) => g.count > 0)
    : []
  const previewBody = preview ? (
    preview.assets.length === 0 ? (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={(
        <span>{TREE_EMPTY_TITLE}<br />
          <Text type="secondary" style={{ fontSize: 12 }}>{TREE_EMPTY_HINT}</Text>
        </span>
      )} />
    ) : (
      <>
        <Text strong style={{ display: 'block', marginBottom: 8 }}>
          {`共识别 ${preview.assets.length} 项资产 · ${groups.map((g) => `${typeLabel(g.type)} ${g.count}`).join(' · ')}`}
        </Text>
        {(expanded ? preview.assets : preview.assets.slice(0, 20)).map((a) => assetRow(a))}
        {preview.assets.length > 20 ? (
          <Button type="link" onClick={() => setExpanded((v) => !v)}>
            {expanded ? '收起' : `展开全部 ${preview.assets.length}`}
          </Button>
        ) : null}
        {preview.skipped.length > 0 ? (
          <div style={{ marginTop: 12 }}>
            <Text type="secondary">已跳过 {preview.skipped.length} 个文件</Text>
            <div style={{ marginTop: 4 }}>
              {preview.skipped.map((s) => (
                <div key={s.path} style={{ fontSize: 12 }}>
                  <Text code>{s.path}</Text>
                  <Text type="secondary">（{s.reason}）</Text>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </>
    )
  ) : null

  const resultBody = result ? (
    <>
      <Text strong style={{ display: 'block', marginBottom: 8 }}>
        {`导入完成：新建 ${result.created} · 更新 ${result.updated} · 失败 ${result.failed.length}`}
      </Text>
      {result.failed.map((f) => (
        <div key={f.name} style={{ padding: '4px 0' }}>
          <Tag color="warning">失败</Tag>
          <Text code>{f.name}</Text>
          <Text type="warning">{f.reason}</Text>
        </div>
      ))}
      {result.skipped.length > 0 ? (
        <Text type="secondary">已跳过 {result.skipped.length} 个文件（详见预览清单口径）</Text>
      ) : null}
    </>
  ) : null

  const footer = phase === 'select' ? [
    <Button key="cancel" onClick={cancel}>{IMPORT_CANCEL}</Button>,
    <Button key="start" type="primary" disabled={!picked || overLimit} loading={pending}
            onClick={() => { void runPreview() }}>
      {TREE_START_PARSE}
    </Button>,
  ] : phase === 'preview' ? [
    <Button key="cancel" disabled={pending} onClick={cancel}>{IMPORT_CANCEL}</Button>,
    <Button key="confirm" type="primary" loading={pending}
            disabled={!preview || preview.assets.length === 0}
            onClick={() => { void runConfirm() }}>
      {`确认导入 ${preview?.assets.length ?? 0} 项`}
    </Button>,
  ] : [
    <Button key="reselect" onClick={reselect}>{IMPORT_RESELECT}</Button>,
    <Button key="finish" type="primary" onClick={onFinished}>{IMPORT_FINISH}</Button>,
  ]

  return (
    <Modal
      title={TREE_SELECT_DIR}
      open={open}
      onCancel={cancel}
      footer={footer}
      mask={{ closable: false }}
      destroyOnHidden
    >
      <Steps
        size="small"
        current={phase === 'select' ? 0 : phase === 'preview' ? 1 : 2}
        items={[{ title: IMPORT_STEP_SELECT }, { title: '导入预览' }, { title: IMPORT_STEP_RESULT }]}
        style={{ marginBottom: 16 }}
      />
      {phase === 'select' ? selectBody : phase === 'preview' ? previewBody : resultBody}
    </Modal>
  )
}

export default ImportTreePicker
