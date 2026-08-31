import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    {/* U1-5：antd 中文化（空态/分页/日期等组件文案默认英文） */}
    <ConfigProvider locale={zhCN}>
      <App />
    </ConfigProvider>
  </React.StrictMode>
);

// If you want to start measuring performance with reportWebVitals (for example
// to pass on to console or send to an analytics endpoint), pass a function
// to log results (for example: reportWebVitals(console.log))
// or learn more: https://bit.ly/CRA-vitals
reportWebVitals();
