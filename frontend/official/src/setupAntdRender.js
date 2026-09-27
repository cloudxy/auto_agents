/**
 * Jest setupFiles：在测试文件 import render 之前包 StyleProvider + ConfigProvider。
 * 与 admin 同款：cssinjs mock:'server' 跳过 jsdom 插 style，并关掉 antd 6 动效。
 */
jest.mock('@testing-library/react', () => {
  const React = require('react');
  const { ConfigProvider } = require('antd');
  const { StyleProvider, createCache } = require('@ant-design/cssinjs');
  const actual = jest.requireActual('@testing-library/react');
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
            UserWrapper ? React.createElement(UserWrapper, null, children) : children,
          ),
        );
      return actual.render(ui, { ...options, wrapper });
    },
  };
});
