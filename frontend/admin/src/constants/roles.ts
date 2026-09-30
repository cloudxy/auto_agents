/** 企业内角色的中文名（顶栏身份标签、成员管理共用一份；接口仍传英文码） */
export const TENANT_ROLE_LABELS: Record<string, string> = {
  owner: '企业负责人',
  admin: '管理员',
  operator: '操作员',
  viewer: '只读成员',
}

export const tenantRoleLabel = (role?: string | null): string =>
  (role && TENANT_ROLE_LABELS[role]) || role || '-'
