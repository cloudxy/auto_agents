/**
 * ESLint flat config：接替 CRA 构建期内置的 eslint-config-react-app（official 同构）
 *
 * - @eslint/js + typescript-eslint 推荐集（不做类型感知，保持秒级；类型错误由 tsc --noEmit 兜）
 * - react-hooks：rules-of-hooks 报错、exhaustive-deps 警告，与 react-app 同级
 * - 未用变量 / 表达式语句沿用 react-app 口径：_ 前缀与 catch 参数不算未用，短路与三元语句放行
 * - 只有 error 让 npm run lint 非零退出；warning 照常打印（同 CRA 构建）
 */
import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default defineConfig([
  globalIgnores(['build/', 'coverage/', 'playwright-report/', 'test-results/']),
  {
    files: ['**/*.{js,jsx,mjs,cjs,ts,tsx,mts,cts}'],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    plugins: { 'react-hooks': reactHooks },
    languageOptions: { globals: globals.browser },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrors: 'none',
        ignoreRestSiblings: true,
      }],
      '@typescript-eslint/no-unused-expressions': ['error', {
        allowShortCircuit: true,
        allowTernary: true,
        allowTaggedTemplates: true,
      }],
    },
  },
  {
    // Jest：jest.mock 工厂里只能 require（工厂被提升到 import 之前），测试也会 require('fs') 读源码断言
    files: ['src/**/*.test.{ts,tsx}', 'src/setup*.{js,ts}', 'src/testUtils.tsx', 'src/__mocks__/**'],
    languageOptions: { globals: { ...globals.jest, ...globals.node } },
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
  {
    files: ['*.config.{ts,mts,mjs}', 'e2e/**'],
    languageOptions: { globals: globals.node },
  },
])
