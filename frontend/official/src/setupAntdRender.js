/**
 * Jest setupFiles：在测试文件 import render 之前包 StyleProvider + ConfigProvider + FeedbackProvider。
 * 与 admin 同款：cssinjs mock:'server' 跳过 jsdom 插 style，并关掉 antd 6 动效。
 */
jest.mock('@testing-library/react', () => {
  const React = require('react');
  const { ConfigProvider } = require('antd');
  const { StyleProvider, createCache } = require('@ant-design/cssinjs');
  const actual = jest.requireActual('@testing-library/react');
  // 与生产根部同路径：message / modal 走 App 实例（feedback.tsx），不经 antd 静态方法。
  // 用例 jest.mock 了 feedback 而工厂没带 FeedbackProvider 时退回不包，避免 wrapper 自己炸。
  const { FeedbackProvider = React.Fragment } = require('./feedback');
  const cache = createCache();
  ConfigProvider.config({ theme: { token: { motion: false } } });
  return {
    ...actual,
    render: (ui, options = {}) => {
      const UserWrapper = options.wrapper;
      const wrapper = ({ children }) =>
        React.createElement(
          StyleProvider,
          { cache, mock: 'server', hashPriority: 'high' },
          React.createElement(
            ConfigProvider,
            { theme: { token: { motion: false } }, wave: { disabled: true } },
            React.createElement(
              FeedbackProvider,
              null,
              UserWrapper ? React.createElement(UserWrapper, null, children) : children,
            ),
          ),
        );
      return actual.render(ui, { ...options, wrapper });
    },
  };
});
