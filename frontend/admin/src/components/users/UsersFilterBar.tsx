/**
 * 用户管理筛选栏（决策 D11：筛选全部走服务端，状态与取数在页面里；本组件只负责展示与回调）
 */
import React from 'react'
import { Button, Input, Select, Space } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { DepartmentRow } from '../../services/rbac'
import type { TenantRow } from '../../services/platformOps'

export interface UsersFilterBarProps {
  searchInput: string
  onSearchInputChange: (v: string) => void
  /** 回车 / 点搜索 / 清空时提交搜索词 */
  onSearch: (v: string) => void
  role: string
  onRoleChange: (v: string) => void
  tenant: number | 'all'
  onTenantChange: (v: number | 'all') => void
  dept: number | 'all'
  onDeptChange: (v: number | 'all') => void
  status: string
  onStatusChange: (v: string) => void
  tenants: TenantRow[]
  departments: DepartmentRow[]
  onCreate: () => void
}

export const UsersFilterBar: React.FC<UsersFilterBarProps> = ({
  searchInput, onSearchInputChange, onSearch, role, onRoleChange, tenant, onTenantChange,
  dept, onDeptChange, status, onStatusChange, tenants, departments, onCreate,
}) => (
  <Space wrap>
    <Input.Search placeholder="搜索用户名/邮箱" allowClear style={{ width: 180 }}
                  value={searchInput}
                  onChange={(e) => onSearchInputChange(e.target.value)}
                  onSearch={(v) => onSearch(v.trim())} />
    <Select size="small" style={{ width: 110 }} value={role} onChange={onRoleChange}
            options={[
              { value: 'all', label: '全部角色' },
              { value: 'admin', label: '管理员' },
              { value: 'operator', label: '操作员' },
              { value: 'viewer', label: '只读' },
            ]} />
    <Select size="small" style={{ width: 130 }} value={tenant} onChange={onTenantChange}
            options={[
              { value: 'all', label: '全部公司' },
              ...tenants.map((tt) => ({ value: tt.id, label: tt.name })),
            ]} />
    <Select size="small" style={{ width: 110 }} value={dept}
            onChange={onDeptChange} disabled={tenant === 'all'}
            options={[
              { value: 'all', label: '全部部门' },
              ...departments.map((d) => ({ value: d.id, label: d.name })),
            ]} />
    <span data-testid="status-filter">
      <Select size="small" style={{ width: 110 }} value={status} onChange={onStatusChange}
              options={[
                { value: 'all', label: '在职（全部）' },
                { value: 'active', label: '在职·激活' },
                { value: 'disabled', label: '已停用' },
                { value: 'deleted', label: '已删除' },
              ]} />
    </span>
    <Button type="primary" icon={<PlusOutlined />} onClick={onCreate}>新建用户</Button>
  </Space>
)
