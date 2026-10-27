import { API_BASE_URL } from '../../../config/api'
import type { SystemStatus } from '../types'

export async function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  const response = await fetch(`${API_BASE_URL}/api/v1/system/status`, { signal })
  if (!response.ok) throw new Error(`System status is unavailable (${response.status}).`)
  return (await response.json()) as SystemStatus
}
