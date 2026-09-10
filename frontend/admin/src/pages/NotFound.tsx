/**
 * 404 页（工单 69）：未匹配路由的明确兜底（替代静默重定向）
 */
import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'

const NotFound = () => {
  const navigate = useNavigate()
  return (
    <Result
      status="404"
      title="404"
      subTitle="页面不存在或已被移除"
      extra={
        <Button type="primary" onClick={() => navigate('/dashboard')}>
          返回工作台
        </Button>
      }
    />
  )
}

export default NotFound
