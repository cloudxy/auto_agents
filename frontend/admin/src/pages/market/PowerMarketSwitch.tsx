/**
 * T-10 屏 24：超管市场总开关。租户货架不挂本控件。禁定价可买四字。
 */
import React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Skeleton, Space, Switch, Typography, message } from 'antd'

import { getPowerMarket, putPowerMarket } from '../../services/capabilities'
import { apiErrorMessage } from '../../utils/errorMessage'

const { Text } = Typography

const SWITCH_LABEL = '能力市场'
const OPENED = '已打开能力市场'
const CLOSED = '已关闭能力市场'
const READ_FAIL = '市场开关暂时无法读取'
const OFFLINE = '网络不可用，市场开关没有改变。'
const SAVING = '保存中…'

const PowerMarketSwitch: React.FC = () => {
  const client = useQueryClient()
  const query = useQuery({
    queryKey: ['admin', 'power-market'],
    queryFn: getPowerMarket,
    retry: false,
  })
  const mutation = useMutation({
    mutationFn: (enabled: boolean) => putPowerMarket(enabled),
    onSuccess: (data) => {
      message.success(data.enabled ? OPENED : CLOSED)
      void client.invalidateQueries({ queryKey: ['admin', 'power-market'] })
    },
    onError: (err) => {
      const offline = typeof navigator !== 'undefined' && navigator.onLine === false
      message.error(offline ? OFFLINE : apiErrorMessage(err, '市场开关没有改变'))
    },
  })

  if (query.isLoading) {
    return (
      <Space align="center" data-testid="power-market-switch-skel" aria-busy="true">
        <Text>{SWITCH_LABEL}</Text>
        <Skeleton.Button size="small" active />
      </Space>
    )
  }
  if (query.isError) {
    return (
      <Alert
        type="error"
        showIcon
        title={READ_FAIL}
        action={<Button size="small" autoInsertSpace={false} onClick={() => { void query.refetch() }}>重试</Button>}
      />
    )
  }
  const enabled = query.data?.enabled === true
  return (
    <Space align="center" data-testid="power-market-switch">
      <Text>{SWITCH_LABEL}</Text>
      <Switch
        checked={enabled}
        checkedChildren="开"
        unCheckedChildren="关"
        disabled={mutation.isPending}
        loading={mutation.isPending}
        onChange={(next) => mutation.mutate(next)}
        aria-label={SWITCH_LABEL}
      />
      {mutation.isPending ? <Text type="secondary">{SAVING}</Text> : null}
    </Space>
  )
}

export default PowerMarketSwitch
