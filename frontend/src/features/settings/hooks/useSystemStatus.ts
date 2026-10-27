import { useCallback, useEffect, useState } from 'react'
import { fetchSystemStatus } from '../api/systemClient'
import type { SystemStatus } from '../types'

export function useSystemStatus() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), [])
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    void fetchSystemStatus(controller.signal).then(setStatus)
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Backend is unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [refreshKey])
  return { status, loading, error, refresh }
}
