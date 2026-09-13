/**
 * Jest setupFiles：在测试文件 import render 之前包 StyleProvider + ConfigProvider。
 * jsdom 解析不了 antd 6 的 CSS-in-JS（Could not parse CSS stylesheet），每次注入都抛；
 * mock:'server' 跳过插 style。再关 motion，避免 Modal/Form 把单测拖到 30s+。
 * setupTests 里改 rtl.render 会撞只读 getter，必须走 jest.mock。
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
