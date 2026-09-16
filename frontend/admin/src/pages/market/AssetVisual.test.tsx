/**
 * T-09（FR-06）：占位确定性（GWT-06.1 两次渲染一致）、真图不占位（06.2）、
 * 损坏回落（06.3 onError → 占位，不报错）。
 */
import React from 'react'
import { fireEvent, render } from '@testing-library/react'

import AssetVisual, { hashKey, visualIndex } from './AssetVisual'

test('GWT-06.1 同一资产两次渲染视觉一致（纯函数 + DOM 同渐变序号）', () => {
  const first = visualIndex('skill', 'check-arch')
  const second = visualIndex('skill', 'check-arch')
  expect(first).toBe(second)
  const { rerender, getByTestId } = render(
    <AssetVisual assetType="skill" name="check-arch" title="架构合规检查" />,
  )
  expect(getByTestId('asset-visual').getAttribute('data-visual-index')).toBe(String(first))
  rerender(<AssetVisual assetType="skill" name="check-arch" title="架构合规检查" />)
  expect(getByTestId('asset-visual').getAttribute('data-visual-index')).toBe(String(first))
  // hash 输入含 type+name：不同 key 不同 hash（mod 8 允许偶发同序号，属确定性分桶）
  expect(hashKey('skill:a')).not.toBe(hashKey('plugin:a'))
})

test('GWT-06.1 渐变序号稳定落在 0–7 且不含随机源', () => {
  for (const type of ['skill', 'plugin', 'command', 'agent', 'team']) {
    for (const name of ['alpha', 'beta', 'gamma', 'dev-team__child']) {
      const idx = visualIndex(type, name)
      expect(idx).toBeGreaterThanOrEqual(0)
      expect(idx).toBeLessThanOrEqual(7)
      expect(visualIndex(type, name)).toBe(idx)
    }
  }
})

test('GWT-06.2 有 logo 渲染 <img> 真图，不出现占位渐变', () => {
  const { getByTestId, container } = render(
    <AssetVisual assetType="plugin" name="dev-team" logo="/api/v1/public/capabilities/plugin/dev-team/media/logo" />,
  )
  expect(container.querySelector('img')).toHaveAttribute(
    'src', '/api/v1/public/capabilities/plugin/dev-team/media/logo',
  )
  expect(getByTestId('asset-visual').className).not.toMatch(/asset-visual--grad-/)
})

test('GWT-06.3 图损坏 onError 回落占位，页面不报错', () => {
  const { container, getByTestId } = render(
    <AssetVisual assetType="skill" name="broken-img" logo="/broken/logo.png" />,
  )
  const img = container.querySelector('img') as HTMLImageElement
  expect(img).toBeInTheDocument()
  fireEvent.error(img)
  expect(container.querySelector('img')).toBeNull()
  expect(getByTestId('asset-visual').className).toMatch(/asset-visual--grad-/)
})

test('占位含展示名首字符与类型角标（第二通道为图标形非色相）', () => {
  const { getByTestId } = render(
    <AssetVisual assetType="skill" name="db-design__x" title="数据库设计流水线" />,
  )
  const v = getByTestId('asset-visual')
  expect(v.textContent).toContain('数')
  expect(v.querySelector('.asset-visual__chip')).toBeTruthy()
})
