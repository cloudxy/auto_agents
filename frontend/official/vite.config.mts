/**
 * official 构建 / 开发服务器配置（由 CRA 迁移，与 admin 同构）
 *
 * - 产物目录 build/：Dockerfile、scripts/runlib、Playwright webServer 都按此路径取
 * - 开发端口取 PORT（scripts/runlib/frontend.py 注入，.env 也可写），缺省 9113；
 *   只监听 127.0.0.1，端口被占直接失败（strictPort），不悄悄换端口
 * - /api 反代后端（API_PROXY_TARGET，缺省 http://127.0.0.1:9111），取代 CRA 的 src/setupProxy.js
 * - 源码与 Jest 继续读 process.env.REACT_APP_*：按 CRA 同一套 .env 文件静态替换，未设置即 undefined
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

const APP_DIR = fileURLToPath(new URL('.', import.meta.url))
const DEFAULT_PORT = 9113
const DEFAULT_API_TARGET = 'http://127.0.0.1:9111'
// 产物语法下限对齐 antd 6 自身（CSS-in-JS 的 :where() 需 Chrome/Edge 88、Firefox 78、Safari 14）；
// Vite 8 缺省 baseline-widely-available（Safari 16 / Chrome 107）会把 iOS 15 等设备挡在外面
const BROWSER_TARGET = ['es2020', 'chrome88', 'edge88', 'firefox78', 'safari14']
const ENV_REF = /process\.env\.(REACT_APP_[A-Z0-9_]+)/g

/** src 里引用过的 REACT_APP_* 键：没配值的也要替换成 undefined，否则浏览器里 process 未定义直接白屏 */
function referencedEnvKeys(dir: string): string[] {
  const keys = new Set<string>()
  for (const file of readdirSync(dir, { recursive: true, encoding: 'utf8' })) {
    if (!/\.[jt]sx?$/.test(file)) continue
    for (const match of readFileSync(join(dir, file), 'utf8').matchAll(ENV_REF)) keys.add(match[1])
  }
  return [...keys]
}

function processEnvDefine(env: Record<string, string>): Record<string, string> {
  const keys = new Set([...referencedEnvKeys(join(APP_DIR, 'src')), ...Object.keys(env)])
  return Object.fromEntries(
    [...keys]
      .filter((key) => key.startsWith('REACT_APP_'))
      .map((key) => [`process.env.${key}`, key in env ? JSON.stringify(env[key]) : 'undefined']),
  )
}

export default defineConfig(({ mode }) => {
  // 优先级（高 → 低）：进程环境变量 > .env.[mode].local > .env.[mode] > .env.local > .env。
  // 注意与 CRA 不同：CRA 里 .env.local 压过 .env.development，Vite 里反过来——
  // 本地开发要覆盖已提交的 .env.development，写进 .env.development.local。
  const env = loadEnv(mode, APP_DIR, ['REACT_APP_', 'PORT', 'API_PROXY_TARGET'])
  return {
    root: APP_DIR,
    envDir: APP_DIR,
    plugins: [react()],
    define: processEnvDefine(env),
    server: {
      host: '127.0.0.1',
      port: Number(env.PORT) || DEFAULT_PORT,
      strictPort: true,
      proxy: {
        // 只代理 /api 路径段（/api、/api/…、/api?…）：字符串键 '/api' 是前缀匹配，会把 /api-keys、
        // /api_keys 这类前端路由也转给后端（CRA setupProxy 按路径段匹配，不会）
        '^/api(?=/|\\?|$)': { target: env.API_PROXY_TARGET || DEFAULT_API_TARGET, changeOrigin: true },
      },
    },
    build: { outDir: 'build', target: BROWSER_TARGET },
  }
})
