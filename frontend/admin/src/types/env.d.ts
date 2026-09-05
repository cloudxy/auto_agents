/**
 * 环境变量类型定义
 */
declare global {
  namespace NodeJS {
    interface ProcessEnv {
      REACT_APP_API_BASE_URL: string
      REACT_APP_ENV: 'development' | 'test' | 'production'
    }
  }
}

export {}
