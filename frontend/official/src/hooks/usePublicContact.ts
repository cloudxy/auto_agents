/**
 * 读公开联系方式（决策 D25）；失败不抛错（联系入口降级），不依赖 QueryClientProvider
 */
import { useEffect, useState } from 'react'
import type { PublicContact } from '@auto-agents/frontend-shared'
import { fetchPublicContact } from '../services/contact'

export function usePublicContact(): PublicContact | null {
  const [contact, setContact] = useState<PublicContact | null>(null)
  useEffect(() => {
    let alive = true
    fetchPublicContact()
      .then((c) => { if (alive) setContact(c) })
      .catch(() => { if (alive) setContact(null) })
    return () => { alive = false }
  }, [])
  return contact
}
