/** HTTP 错误码辅助：跨企业/缺页 404 同形。 */

type HttpErrLike = { response?: { status?: number; data?: { code?: string } } }

export function isNotFoundError(e: unknown): boolean {
  if (typeof e !== 'object' || e === null) return false
  const r = (e as HttpErrLike).response
  return r?.status === 404 || r?.data?.code === 'NOT_FOUND'
}
