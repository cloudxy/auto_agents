/// <reference types="react-scripts" />

namespace NodeJS {
  interface ProcessEnv {
    /** API 基地址（默认 http://localhost:9111/api/v1） */
    REACT_APP_API_BASE_URL?: string
    /** 管理后台地址（官网"进入控制台"入口，默认 http://localhost:9112） */
    REACT_APP_ADMIN_URL?: string
    /** 平台联系邮箱（定价付费档 mailto；无品牌邮箱时本地占位） */
    REACT_APP_CONTACT_MAIL?: string
    /** 环境标识（local/dev/prod） */
    REACT_APP_ENV?: string
  }
}
