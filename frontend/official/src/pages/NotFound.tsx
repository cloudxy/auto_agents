/**
 * 404 页（工单 70）
 */
import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'

const NotFound = () => {
  const navigate = useNavigate()
  return (
    <Result
      status="404"
      title="404"
      subTitle="页面不存在，可能已被移除或地址有误"
      extra={
        <Button type="primary" onClick={() => navigate('/')}>
          返回首页
        </Button>
      }
      style={{ padding: '96px 24px' }}
    />
  )
}

export default NotFound
