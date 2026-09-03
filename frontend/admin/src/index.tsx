import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BRAND_TOKENS } from '@auto-agents/frontend-shared';
import zhCN from 'antd/locale/zh_CN';
import './index.css';
import App from './App';

// 工单 78：react-query 全局客户端（轮询/缓存/失焦暂停统一托管）
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    {/* U1-5：antd 中文化（空态/分页/日期等组件文案默认英文） */}
    <QueryClientProvider client={queryClient}>
    <ConfigProvider
      locale={zhCN}
      theme={{
        // 工单 77（D7）：语义色单源（shared BRAND_TOKENS）——品牌换色只改 shared
        token: {
          colorPrimary: BRAND_TOKENS.primary,
          colorSuccess: BRAND_TOKENS.success,
          colorWarning: BRAND_TOKENS.warning,
          colorError: BRAND_TOKENS.danger,
          colorInfo: BRAND_TOKENS.primary,
        },
      }}
    >
      <App />
    </ConfigProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
