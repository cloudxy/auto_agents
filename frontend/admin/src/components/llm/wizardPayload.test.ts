import { buildWizardPayload, resolveWizardModel } from './wizardPayload'

test('edit save does not throw when values.model is missing', () => {
  const payload = buildWizardPayload(
    { name: '主用', base_url: 'https://api.anthropic.com', provider_type: 'anthropic' },
    {
      id: 1, name: '主用', base_url: 'https://api.anthropic.com',
      model: 'claude-sonnet-4-6', enabled: true, is_active: true,
    },
  )
  expect(payload).not.toBeNull()
  expect(payload?.model).toBe('claude-sonnet-4-6')
  expect(payload?.name).toBe('主用')
})

test('create without model returns null instead of calling trim on undefined', () => {
  expect(resolveWizardModel({}, null)).toBe('')
  expect(buildWizardPayload({ name: 'x', base_url: 'https://x' }, null)).toBeNull()
})
