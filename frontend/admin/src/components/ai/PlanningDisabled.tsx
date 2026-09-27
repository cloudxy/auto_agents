/**
 * FR-M01 规划未开放金标（打开/提交同一句）+ 去采集任务。
 */
import React from 'react'
import { Button } from 'antd'
import { useNavigate } from 'react-router-dom'
import { LoadEmpty } from '../LoadState'
import { GO_COLLECT_TASKS, PLANNING_DISABLED_COPY } from '../../constants/collectCopy'

export const PlanningDisabledBanner: React.FC = () => {
  const navigate = useNavigate()
  return (
    <LoadEmpty
      title={PLANNING_DISABLED_COPY}
      style={{ marginBottom: 16 }}
      action={(
        <Button type="primary" size="small" onClick={() => navigate('/spiders/tasks')}>
          {GO_COLLECT_TASKS}
        </Button>
      )}
    />
  )
}

export default PlanningDisabledBanner
