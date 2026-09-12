/**
 * T-36 一键导入向导（FR-100 UI 半 / ADR-0023）：选来源（文件/目录二选一互斥）→
 * 结果清单 → 完成。部分成功逐条中文原因（GWT-100.2/100.5/100.7）；跳过标记
 * 「已存在，跳过」（100.8）；空批次中性句（100.3）；产物未上架不执行（PC-2）；
 * 入口仅超管（100.6，由父层守卫隐藏）。上传/解析 loading 态；网络句保留所选。
 */
import React, { useRef, useState } from 'react'
import {
  Alert, Button, Empty, Input, Modal, Skeleton, Space, Steps, Tag, Typography, theme,
} from 'antd'
import {
  AppstoreOutlined, CodeOutlined, FolderOpenOutlined, QuestionOutlined,
  RobotOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import type { AxiosProgressEvent } from 'axios'

import { importAssets, type ImportItemResult, type ImportResult } from '../../services/capabilities'
import { apiErrorMessage } from '../../utils/errorMessage'
import {
  IMPORT_CANCEL, IMPORT_CHOOSE_HINT, IMPORT_DIR_LABEL, IMPORT_DIR_PLACEHOLDER,
  IMPORT_EMPTY_BATCH, IMPORT_ENTRY, IMPORT_EXCLUSIVE, IMPORT_FINISH, IMPORT_NETWORK_FAIL,
  IMPORT_PARSING, IMPORT_PARSE_RETRY, IMPORT_RESELECT, IMPORT_RETRY, IMPORT_SELECT,
  IMPORT_START, IMPORT_STATUS_FAIL, IMPORT_STATUS_OK, IMPORT_STATUS_SKIP,
  IMPORT_STEP_RESULT, IMPORT_STEP_SELECT, IMPORT_TYPE_LABELS, IMPORT_UNLISTED_NOTE,
  IMPORTING, parseFailCopy, summaryCopy, uploadingCopy,
} from './importWizardCopy'

const { Text } = Typography

type Failure = { kind: 'network' | 'parse'; text: string }

type Props = {
  open: boolean
  /** 取消/右上关闭：imported = 本轮已有成功导入，父层据此刷新目录 */
  onCancel: (imported: boolean) => void
  /** 完成：关闭 + 刷新目录 + 切到目录 tab（完成反馈含类型与名称） */
  onFinished: () => void
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  skill: <ThunderboltOutlined />,
  command: <CodeOutlined />,
  agent: <RobotOutlined />,
  plugin: <AppstoreOutlined />,
}

const typeLabel = (t: string): string => IMPORT_TYPE_LABELS[t] || t

const hasResponse = (e: unknown): boolean => (
  typeof e === 'object' && e !== null
  && 'response' in e && (e as { response?: unknown }).response != null
)

const statusTag = (status: string): React.ReactNode => {
  if (status === 'succeeded') return <Tag color="success">{IMPORT_STATUS_OK}</Tag>
  if (status === 'skipped') return <Tag>{IMPORT_STATUS_SKIP}</Tag>
  return <Tag color="error">{IMPORT_STATUS_FAIL}</Tag>
}

// antd v6 已弃用 List 组件：结果清单用普通行渲染（type 徽标 + 名称 + 逐条原因 + 状态）
const resultItem = (item: ImportItemResult, index: number): React.ReactNode => (
  <div
    key={`${item.asset_type}-${item.name}-${index}`}
    style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '6px 0' }}
  >
    <Tag icon={TYPE_ICONS[item.asset_type] || <QuestionOutlined />}>
      {typeLabel(item.asset_type)}
    </Tag>
    <div style={{ flex: 1, minWidth: 0, overflowWrap: 'break-word' }}>
      <Text code>{item.name}</Text>
      {item.status === 'failed' && item.reason ? (
        <div>
          <Text type="danger">{item.reason}</Text>
        </div>
      ) : null}
    </div>
    {statusTag(item.status)}
  </div>
)

const ImportWizard: React.FC<Props> = ({ open, onCancel, onFinished }) => {
  const [phase, setPhase] = useState<'select' | 'result'>('select')
  const [files, setFiles] = useState<File[]>([])
  const [directory, setDirectory] = useState('')
  const [pending, setPending] = useState(false)
  const [uploadPercent, setUploadPercent] = useState<number | null>(null)
  const [parsing, setParsing] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const fileInput = useRef<HTMLInputElement | null>(null)
  const { token } = theme.useToken()

  const hasFiles = files.length > 0
  const hasDirectory = directory.trim().length > 0
  const hasSource = hasFiles || hasDirectory
  const imported = Boolean(result && result.succeeded > 0)

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFiles(Array.from(e.target.files || []))
    e.target.value = ''
  }

  const removeFile = (index: number) => setFiles(files.filter((_, i) => i !== index))

  const reselect = () => {
    setPhase('select')
    setFiles([])
    setDirectory('')
    setFailure(null)
    setResult(null)
  }

  const trackUpload = (event: AxiosProgressEvent) => {
    if (!event.total) return
    const percent = Math.min(100, Math.round((event.loaded / event.total) * 100))
    setUploadPercent(percent)
    if (percent >= 100) setParsing(true)
  }

  const submit = async () => {
    if (!hasSource || pending) return
    setPending(true)
    setFailure(null)
    setUploadPercent(null)
    setParsing(false)
    try {
      const data = await importAssets(
        hasFiles ? { files } : { directory: directory.trim() },
        hasFiles ? trackUpload : undefined,
      )
      setResult(data)
      setPhase('result')
    } catch (e) {
      if (hasResponse(e)) {
        setFailure({
          kind: 'parse',
          text: parseFailCopy(apiErrorMessage(e, IMPORT_PARSE_RETRY)),
        })
      } else {
        setFailure({ kind: 'network', text: IMPORT_NETWORK_FAIL })
      }
    } finally {
      setPending(false)
      setUploadPercent(null)
      setParsing(false)
    }
  }

  const progressText = parsing
    || (uploadPercent !== null && uploadPercent >= 100)
    ? IMPORT_PARSING
    : (uploadPercent !== null ? uploadingCopy(uploadPercent) : IMPORTING)

  const selectBody = (
    <>
      {failure ? (
        <Alert
          type="error"
          showIcon
          title={failure.text}
          style={{ marginBottom: 12 }}
          action={failure.kind === 'network' ? (
            <Button size="small" disabled={!hasSource || pending} onClick={submit}>
              {IMPORT_RETRY}
            </Button>
          ) : (
            <Button size="small" onClick={reselect}>{IMPORT_RESELECT}</Button>
          )}
        />
      ) : null}
      {!hasSource && !pending ? (
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          {IMPORT_CHOOSE_HINT}
        </Text>
      ) : null}
      <Space direction="vertical" size="middle" style={{ width: '100%' }} aria-live="polite">
        <div>
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".md,.zip"
            style={{ display: 'none' }}
            onChange={onPick}
            data-testid="import-file-input"
          />
          <Space wrap>
            <Button
              icon={<FolderOpenOutlined />}
              disabled={hasDirectory || pending}
              onClick={() => fileInput.current?.click()}
            >
              {IMPORT_SELECT}
            </Button>
            {hasDirectory ? <Text type="secondary">{IMPORT_EXCLUSIVE}</Text> : null}
          </Space>
          {hasFiles ? (
            <div style={{ marginTop: 8 }}>
              {files.map((f, i) => (
                <Tag key={`${f.name}-${i}`} closable onClose={() => removeFile(i)}>{f.name}</Tag>
              ))}
            </div>
          ) : null}
        </div>
        <div>
          <label htmlFor="import-directory" style={{ display: 'block' }}>
            {IMPORT_DIR_LABEL}
          </label>
          <Input
            id="import-directory"
            value={directory}
            disabled={hasFiles || pending}
            placeholder={IMPORT_DIR_PLACEHOLDER}
            onChange={(e) => setDirectory(e.target.value)}
            style={{ marginTop: 4 }}
          />
          {hasFiles ? <Text type="secondary">{IMPORT_EXCLUSIVE}</Text> : null}
        </div>
      </Space>
      {pending ? (
        <div style={{ marginTop: 16 }} aria-live="polite">
          <Text>{progressText}</Text>
          {parsing ? <Skeleton active paragraph={{ rows: 3 }} style={{ marginTop: 8 }} /> : null}
        </div>
      ) : null}
    </>
  )

  const resultBody = result && result.total === 0 ? (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={IMPORT_EMPTY_BATCH} />
  ) : result ? (
    <>
      <Text strong style={{ display: 'block', marginBottom: 8 }}>
        {summaryCopy(result.succeeded, result.failed, result.skipped)}
      </Text>
      {result.succeeded > 0 ? (
        <Alert
          type="info"
          showIcon
          title={IMPORT_UNLISTED_NOTE}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      <div style={{ borderTop: `1px solid ${token.colorBorderSecondary}` }}>
        {result.items.map(resultItem)}
      </div>
    </>
  ) : null

  const footer = phase === 'select' ? [
    <Button key="cancel" onClick={() => onCancel(imported)}>{IMPORT_CANCEL}</Button>,
    <Button
      key="start"
      type="primary"
      disabled={!hasSource}
      loading={pending}
      onClick={submit}
    >
      {pending ? IMPORTING : IMPORT_START}
    </Button>,
  ] : [
    <Button key="reselect" onClick={reselect}>{IMPORT_RESELECT}</Button>,
    <Button key="finish" type="primary" onClick={onFinished}>{IMPORT_FINISH}</Button>,
  ]

  return (
    <Modal
      title={IMPORT_ENTRY}
      open={open}
      onCancel={() => onCancel(imported)}
      footer={footer}
      mask={{ closable: false }}
      destroyOnHidden
    >
      <Steps
        size="small"
        current={phase === 'select' ? 0 : 1}
        items={[{ title: IMPORT_STEP_SELECT }, { title: IMPORT_STEP_RESULT }]}
        style={{ marginBottom: 16 }}
      />
      {phase === 'select' ? selectBody : resultBody}
    </Modal>
  )
}

export default ImportWizard
