/**
 * 恢复软删用户弹窗（T-25 / FR-93，edge-states 用户管理屏）
 *
 * - 确认文案：恢复用户 “{用户名}”？/ 恢复后回到用户列表并恢复为启用状态
 * - 占用冲突（GWT-93.4/93.8）：后端 400 中文句前缀映射 → 内联红字两行，弹窗不关，
 *   不渲染内部码（X-QUOTA）；沿用 F-02 前缀映射口径（Members 先例）
 * - 重复恢复（GWT-93.9）：后端幂等 no-op 且 200 返回在册快照——真恢复必置
 *   is_active=true，故「在册且停用」只可能是 no-op 残留（可判定面的保守信号）→
 *   不报成功，静默刷新；并发恢复抢先的快照与真恢复同形，按成功处理（结果为真）
 * - 离线：钉句「网络不可用，用户没有恢复。」弹窗不关（RelayGroups 同口径）
 * - 其他失败：FR-84 族失败句，弹窗不关
 */
import React, { useEffect, useState } from 'react'
import { message, Modal, Typography } from 'antd'
import { restoreUser, type UserItem } from '../services/users'
import { apiErrorMessage } from '../utils/errorMessage'

const CONFLICT_SENTENCE = '用户名或邮箱已被现有用户占用'
const OFFLINE_RESTORE = '网络不可用，用户没有恢复。'

const isOccupancyConflict = (e: unknown): boolean =>
  apiErrorMessage(e, '').startsWith(CONFLICT_SENTENCE)

interface RestoreUserModalProps {
  /** 待恢复行（null=关闭） */
  user: UserItem | null
  onClose: () => void
  /** 结束（成功/幂等）后由宿主刷新列表 */
  onRestored: () => void
}

const RestoreUserModal: React.FC<RestoreUserModalProps> = ({ user, onClose, onRestored }) => {
  const [submitting, setSubmitting] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  // 换行/重开时清残留错误态
  useEffect(() => {
    if (user) {
      setConflict(false)
      setFailure(null)
    }
  }, [user])

  if (!user) return null

  const onOk = async () => {
    // 离线钉句（edge-states 用户管理屏）：不发请求、弹窗不关
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      setConflict(false)
      setFailure(OFFLINE_RESTORE)
      return
    }
    setSubmitting(true)
    setConflict(false)
    setFailure(null)
    try {
      const restored = await restoreUser(user.id)
      const noOp = restored.deleted_at == null && restored.is_active === false
      onClose()
      onRestored()
      if (!noOp) {
        message.success(`已恢复 “${user.username}”。该用户已回到用户列表。`)
      }
    } catch (e) {
      if (isOccupancyConflict(e)) {
        setConflict(true)
      } else {
        setFailure(`恢复失败。${apiErrorMessage(e, '检查网络后重试')}。该用户仍保持已删除。`)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title={`恢复用户 “${user.username}”？`}
      open={!!user}
      onOk={onOk}
      onCancel={onClose}
      confirmLoading={submitting}
      okText={submitting ? '恢复中…' : '恢复'}
      cancelText="取消"
    >
      <p>恢复后该用户回到用户列表并恢复为启用状态，可重新登录。</p>
      {conflict && (
        <Typography.Paragraph type="danger" role="alert">
          {/* 两句钉句各占一个元素：视觉两行，且可被精确断言/朗读各自成句 */}
          <span style={{ display: 'block' }}>用户名或邮箱已被现有用户占用。</span>
          <span style={{ display: 'block' }}>该用户仍保留在已删除列表中。</span>
        </Typography.Paragraph>
      )}
      {failure && (
        <Typography.Paragraph type="danger" role="alert">{failure}</Typography.Paragraph>
      )}
    </Modal>
  )
}

export default RestoreUserModal
