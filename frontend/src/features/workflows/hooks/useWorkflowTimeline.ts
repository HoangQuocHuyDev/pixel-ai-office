import { useCallback, useEffect, useState } from 'react'
import { fetchWorkflowTimeline } from '../api/workflowTimelineClient'
import type { WorkflowTimelineData } from '../types'

const active = (data: WorkflowTimelineData | null) => data?.status === 'pending' || data?.status === 'running'

export function useWorkflowTimeline(workflowId: number, pollMilliseconds = 2500) {
  const [data, setData] = useState<WorkflowTimelineData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), [])
  useEffect(() => {
    let disposed = false; let timer: number | undefined; let controller: AbortController | undefined
    const load = async () => {
      if (document.visibilityState === 'hidden') { timer = window.setTimeout(load, pollMilliseconds); return }
      controller = new AbortController(); setError(null)
      try {
        const next = await fetchWorkflowTimeline(workflowId, controller.signal)
        if (!disposed) { setData(next); setLoading(false) }
        if (!disposed && active(next)) timer = window.setTimeout(load, pollMilliseconds)
      } catch (reason) {
        if (!disposed && !controller.signal.aborted) { setError(reason instanceof Error ? reason.message : 'Timeline is unavailable.'); setLoading(false); timer = window.setTimeout(load, pollMilliseconds) }
      }
    }
    setLoading(true); setData(null); void load()
    return () => { disposed = true; controller?.abort(); if (timer !== undefined) window.clearTimeout(timer) }
  }, [workflowId, pollMilliseconds, refreshKey])
  return { data, loading, error, refresh }
}
