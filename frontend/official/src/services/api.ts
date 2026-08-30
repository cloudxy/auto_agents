/**
 * Axios 实例配置
 */
import axios from 'axios'

const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:9111/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    return Promise.reject(error)
  }
)

export default api
