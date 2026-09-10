/**
 * 无权限页面
 */
import React from 'react'
import { Result, Button } from 'antd'
import { useNavigate } from 'react-router-dom'

const Unauthorized: React.FC = () => {
  const navigate = useNavigate()

  return (
    <Result
      status="403"
      title="403"
      subTitle="抱歉，您没有权限访问该页面。"
      extra={<Button type="primary" onClick={() => navigate('/dashboard')}>返回仪表盘</Button>}
    />
  )
}

export default Unauthorized
