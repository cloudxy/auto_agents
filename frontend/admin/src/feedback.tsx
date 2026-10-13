/**
 * antd 反馈 API 单源：message / notification / modal（official 同构一份）
 *
 * antd 静态方法（message.success、Modal.confirm…）渲染在 React 树外，读不到 ConfigProvider
 * 上下文——品牌主题 token、zh_CN 文案都不生效，antd 6 每次还告警
 * 「Static function can not consume context like dynamic theme」。官方解法是 <App> + App.useApp()，
 * 但 hook 只能在组件里拿，事件回调 / service 结果回调里到处传实例不现实。
 *
 * 本模块把两者接起来：根部 ConfigProvider 内包 <FeedbackProvider>，挂载时把 App.useApp()
 * 的实例登记进来；业务代码一律 `import { message, modal } from '<相对路径>/feedback'`，调用时才取
 * 实例转发。尚未挂载（根外调用、不经根直渲的组件）回退 antd 静态 API，行为与改造前一致。
 *
 * 各应用一份、不进 frontend/shared：shared 是无 React / antd 依赖、无 JSX 编译的纯 TS 包
 * （只 peer axios，经 dist 消费），引进来要动它的依赖与构建；本文件几十行，双份代价更小。
 */
import React, { useLayoutEffect } from 'react'
import { App, Modal, message as staticMessage, notification as staticNotification } from 'antd'

type FeedbackApi = ReturnType<typeof App.useApp>
/** 命令式确认框五件套：App 实例的 modal 与静态 Modal 的公共子集 */
type ModalApi = Record<'info' | 'success' | 'error' | 'warning' | 'confirm', typeof Modal.confirm>

/** 已挂载实例栈：嵌套 Provider（单测 wrapper 套被测根组件）时最内层生效，卸载即出栈 */
const mounted: FeedbackApi[] = []
const current = (): FeedbackApi | undefined => mounted[mounted.length - 1]

function FeedbackBridge(): null {
  const api = App.useApp()
  // layout effect：同一次提交里先于所有 useEffect 执行，首屏 effect 里弹的提示也走实例
  useLayoutEffect(() => {
    mounted.push(api)
    return () => {
      const i = mounted.lastIndexOf(api)
      if (i >= 0) mounted.splice(i, 1)
    }
  }, [api])
  return null
}

/**
 * 放在 ConfigProvider 内、业务树外层。component={false}：不额外包 div，也不带 .ant-app
 * 的排版重置样式——只接上下文，页面 DOM 与样式与改造前一致。
 */
export function FeedbackProvider({ children }: { children?: React.ReactNode }) {
  return (
    <App component={false}>
      <FeedbackBridge />
      {children}
    </App>
  )
}

const pickMessage = (): FeedbackApi['message'] => current()?.message ?? staticMessage
const pickNotification = (): FeedbackApi['notification'] => current()?.notification ?? staticNotification
const pickModal = (): ModalApi => current()?.modal ?? Modal

export const message: FeedbackApi['message'] = {
  open: (args) => pickMessage().open(args),
  info: (...args) => pickMessage().info(...args),
  success: (...args) => pickMessage().success(...args),
  error: (...args) => pickMessage().error(...args),
  warning: (...args) => pickMessage().warning(...args),
  loading: (...args) => pickMessage().loading(...args),
  destroy: (key) => pickMessage().destroy(key),
}

export const notification: FeedbackApi['notification'] = {
  open: (args) => pickNotification().open(args),
  info: (args) => pickNotification().info(args),
  success: (args) => pickNotification().success(args),
  error: (args) => pickNotification().error(args),
  warning: (args) => pickNotification().warning(args),
  destroy: (key) => pickNotification().destroy(key),
}

/** Modal 命令式确认框；声明式 <Modal> 组件照旧从 antd 引入 */
export const modal: ModalApi = {
  info: (props) => pickModal().info(props),
  success: (props) => pickModal().success(props),
  error: (props) => pickModal().error(props),
  warning: (props) => pickModal().warning(props),
  confirm: (props) => pickModal().confirm(props),
}
