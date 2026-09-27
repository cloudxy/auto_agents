/**
 * 页级 tab 上提机制（T-31 / GWT-98.1，FR-99 §0.10 布局 token）：
 * AdminLayout 顶栏行经 PageHeaderSlotContext 开槽；页面用 <PageHeaderTabs> 把
 * 页级 tab 挂到顶栏（页名右侧、与欢迎语同一行）。未包 AdminLayout（单测/
 * 独立渲染）时原位回退渲染 tab，可用性不变。T-34 点名页推广直接复用本件。
 *
 * token（edge-states §0.10，antd 基座不新增视觉体系）：
 * - page-header.tab 14px，选中 600（下方 CSS，无色值硬编码）
 * - page-header.gap 16px（槽位容器 marginLeft 由 AdminLayout 提供）
 * - tab-switch.motion ≤150ms 透明度过渡、无位移（pageTabPaneStyle + keyframes；
 *   内容区 pane 常挂载、display 切换，tab 内筛选/分页状态不丢）
 */
import React, { useContext, useEffect } from 'react'
import { Tabs } from 'antd'

export interface PageHeaderTabItem {
  key: string
  label: React.ReactNode
}

export interface PageHeaderTabBar {
  items: PageHeaderTabItem[]
  activeKey: string
  onChange: (activeKey: string) => void
}

interface PageHeaderSlot {
  setTabBar: (tabBar: PageHeaderTabBar | null) => void
}

/** AdminLayout 提供；页面侧只消费，不直接引用 Header 内部结构 */
export const PageHeaderSlotContext = React.createContext<PageHeaderSlot | null>(null)

/** §0.10 token：页级 tab 字号/选中字重 + 顶栏内 Tabs 去 nav 下边距 + 切换 keyframes */
const PAGE_HEADER_TAB_CSS = `
.page-header-tabs .ant-tabs-nav { margin-bottom: 0; }
.page-header-tabs .ant-tabs-tab-btn { font-size: 14px; }
.page-header-tabs .ant-tabs-tab-active .ant-tabs-tab-btn { font-weight: 600; }
@keyframes page-tab-switch-fade { from { opacity: 0; } to { opacity: 1; } }
`

/**
 * 内容区 pane 容器样式：三 tab 数据装配与挂载时机不变（常挂载），
 * display 切换；显示时 ≤150ms 透明度过渡（token tab-switch.motion，无位移）。
 */
export const pageTabPaneStyle = (active: boolean): React.CSSProperties => ({
  display: active ? 'block' : 'none',
  animation: active ? 'page-tab-switch-fade 150ms ease' : undefined,
})

/**
 * 页级 tab（结构位组件）：挂在页面根部，一次声明。
 * 有槽位 → tab 渲染进 AdminLayout 顶栏行；无槽位 → 原位渲染（回退）。
 * 内容区渲染由页面按 activeKey 自理（配 pageTabPaneStyle）。
 */
const PageHeaderTabs: React.FC<PageHeaderTabBar> = ({ items, activeKey, onChange }) => {
  const slot = useContext(PageHeaderSlotContext)

  useEffect(() => {
    if (!slot) return
    slot.setTabBar({ items, activeKey, onChange })
    return () => slot.setTabBar(null)
  }, [slot, items, activeKey, onChange])

  const tabBar = (
    <Tabs
      activeKey={activeKey}
      onChange={onChange}
      items={items.map(({ key, label }) => ({ key, label }))}
    />
  )

  return (
    <>
      <style>{PAGE_HEADER_TAB_CSS}</style>
      {slot ? null : (
        <div className="page-header-tabs" style={{ marginBottom: 16 }}>{tabBar}</div>
      )}
    </>
  )
}

export default PageHeaderTabs
