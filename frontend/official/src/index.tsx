import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import './tokens.css';
import App from './App';

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    {/* react-query 客户端由 App 持有（工单 78）；这里曾再包一层 QueryClientProvider，内层覆盖外层，外层客户端从未被用到 */}
    <App />
  </React.StrictMode>
);
