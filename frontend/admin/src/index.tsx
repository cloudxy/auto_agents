import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import { QueryClientProvider } from '@tanstack/react-query';
import { BRAND_TOKENS } from '@auto-agents/frontend-shared';
import zhCN from 'antd/locale/zh_CN';
import './index.css';
import App from './App';
// 工单 78：react-query 全局客户端（独立模块：登出时清空缓存）
import { queryClient } from './queryClient';

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
          borderRadius: 8,
          colorBgLayout: '#f5f7fa',
        },
        // 批次 5：侧栏与官网同一深空底，选中项用主色块
        components: {
          Layout: { siderBg: BRAND_TOKENS.deepSpace, headerBg: '#ffffff', bodyBg: '#f5f7fa' },
          Menu: {
            darkItemBg: BRAND_TOKENS.deepSpace,
            darkSubMenuItemBg: '#000c17',
            darkItemSelectedBg: BRAND_TOKENS.primary,
            itemBorderRadius: 6,
          },
          Table: { headerBg: '#fafbfc', headerColor: 'rgba(0,0,0,0.75)' },
          Card: { headerFontSize: 15 },
        },
      }}
    >
      <App />
    </ConfigProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
