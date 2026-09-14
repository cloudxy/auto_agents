import { parseCollectBlock } from './collectBlock'
import {
  PLAN_FULL_COPY,
  SPIDER_WORKER_OFFLINE_CODE,
  SPIDER_WORKER_OFFLINE_COPY,
  STORAGE_CTA,
  TASK_QUOTA_LIMIT_CODE,
  UPGRADE_CTA,
} from '../constants/collectCopy'

test('GWT-U02.2 storage full envelope is quota copy, not worker', () => {
  const block = parseCollectBlock({
    response: {
      status: 400,
      data: {
        code: TASK_QUOTA_LIMIT_CODE,
        message: `${PLAN_FULL_COPY}。${STORAGE_CTA}`,
        data: { dimension: 'storage', cta: STORAGE_CTA },
      },
    },
  })
  expect(block).toEqual({ kind: 'quota', cta: STORAGE_CTA, dimension: 'storage' })
  expect(block && block.kind === 'quota' ? block.cta : '').not.toBe(SPIDER_WORKER_OFFLINE_COPY)
})

test('GWT-U02.4 token full envelope is 申请提升, not worker', () => {
  const block = parseCollectBlock({
    response: {
      status: 400,
      data: {
        code: TASK_QUOTA_LIMIT_CODE,
        message: `${PLAN_FULL_COPY}。${UPGRADE_CTA}`,
        data: { dimension: 'tokens', cta: UPGRADE_CTA },
      },
    },
  })
  expect(block).toEqual({ kind: 'quota', cta: UPGRADE_CTA, dimension: 'tokens' })
})

test('GWT-U02.1 worker envelope is worker copy, not quota', () => {
  const block = parseCollectBlock({
    response: {
      status: 400,
      data: { code: SPIDER_WORKER_OFFLINE_CODE, message: SPIDER_WORKER_OFFLINE_COPY },
    },
  })
  expect(block).toEqual({ kind: 'worker' })
})

test('lock sentences never include 当前可买 or inner codes', () => {
  const blob = [
    PLAN_FULL_COPY, STORAGE_CTA, UPGRADE_CTA, SPIDER_WORKER_OFFLINE_COPY,
  ].join(' ')
  expect(blob).not.toContain('当前可买')
  expect(blob).not.toContain('QUOTA_EXCEEDED')
  expect(blob).not.toMatch(/\b429\b/)
  expect(blob).not.toContain('申请提升配额')
})
