/** 审计 B5-7：不在菜单里的路由也要有正确的页头标题（原先一律回落「后台管理」） */
import { pageTitleFor } from './menuConfig'

test.each([
  ['/pricing', '套餐与定价'],
  ['/billing/checkout', '结账'],
  ['/enterprise', '企业管理'],
  ['/rbac', '组织与角色'],
])('%s → %s', (path, title) => {
  expect(pageTitleFor(path)).toBe(title)
})

test('菜单里的路由仍取菜单名；真正未知的路由才回落', () => {
  expect(pageTitleFor('/dashboard')).not.toBe('后台管理')
  expect(pageTitleFor('/no-such-page')).toBe('后台管理')
})
