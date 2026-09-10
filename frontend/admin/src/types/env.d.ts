/**
 * 环境变量类型定义
 */
declare global {
  namespace NodeJS {
    interface ProcessEnv {
      REACT_APP_API_BASE_URL: string
      REACT_APP_ENV: 'development' | 'test' | 'production'
      /** 官网地址（登录页「企业注册」回链，默认 http://localhost:9113） */
      REACT_APP_OFFICIAL_URL?: string
    }
  }
}

export {}
