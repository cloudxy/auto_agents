/**
 * 用户管理页面 - 陈列系统已有用户（数据来源 /admin/users）
 */
import React, { useEffect, useState } from 'react'
import { Card, Table, Tag, message, Space, Avatar } from 'antd'
import { UserOutlined } from '@ant-design/icons'
import api from '../services/api'

interface UserItem {
  id: number
  username: string
  email: string
  is_active: boolean
  is_admin: boolean
  role?: string
  created_at?: string | null
}

const Users: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [users, setUsers] = useState<UserItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = 20

  const loadUsers = async (p: number) => {
    setLoading(true)
    try {
      // /admin/users 带 ApiResponse 信封，需解包 data
      const res = await api.get<{ items: UserItem[]; total: number }>('/admin/users', {
        params: { skip: (p - 1) * pageSize, limit: pageSize }
      })
      setUsers(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch (error) {
      message.error('获取用户列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers(page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '用户',
      key: 'username',
      render: (_: unknown, record: UserItem) => (
        <Space>
          <Avatar size="small" icon={<UserOutlined />} />
          {record.username}
        </Space>
      ),
    },
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    {
      title: '角色',
      key: 'role',
      width: 100,
      render: (_: unknown, record: UserItem) => {
        // role 为后端新契约；旧数据回退 is_admin 判断
        const role = record.role || (record.is_admin ? 'admin' : 'operator')
        if (role === 'admin') return <Tag color="gold">管理员</Tag>
        if (role === 'viewer') return <Tag>只读</Tag>
        return <Tag color="blue">操作员</Tag>
      },
    },
    {
      title: '状态',
      key: 'is_active',
      width: 100,
      render: (_: unknown, record: UserItem) =>
        record.is_active
          ? <Tag color="green">已激活</Tag>
          : <Tag color="red">未激活</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  ]

  return (
    <Card title={`用户管理（共 ${total} 人）`}>
      <Table
        columns={columns}
        dataSource={users}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: setPage,
          showTotal: (t) => `共 ${t} 位用户`,
        }}
      />
    </Card>
  )
}

export default Users
