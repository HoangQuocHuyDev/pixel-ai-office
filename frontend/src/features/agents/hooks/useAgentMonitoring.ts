import { useCallback, useEffect, useState } from 'react'
import { fetchAgentMonitoring, fetchAgentTimeline, fetchMonitoringSummary } from '../api/agentClient'
import type { AgentId, AgentMonitoring, AgentTimeline, MonitoringSummary } from '../types'

export function useAgentMonitoring(agentId: AgentId, refreshMilliseconds = 10000) {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null)
  const [monitoring, setMonitoring] = useState<AgentMonitoring | null>(null)
  const [timeline, setTimeline] = useState<AgentTimeline | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), [])

  useEffect(() => {
    let disposed = false
    let timer: number | undefined
    let controller: AbortController | undefined
    const load = async () => {
      controller = new AbortController(); setError(null)
      try {
        const [nextSummary, nextMonitoring, nextTimeline] = await Promise.all([
          fetchMonitoringSummary(controller.signal), fetchAgentMonitoring(agentId, controller.signal),
          fetchAgentTimeline(agentId, 0, controller.signal),
        ])
        if (!disposed) { setSummary(nextSummary); setMonitoring(nextMonitoring); setTimeline(nextTimeline); setLoading(false) }
      } catch (reason) {
        if (!disposed && !controller.signal.aborted) { setError(reason instanceof Error ? reason.message : 'Monitoring is unavailable.'); setLoading(false) }
      } finally {
        if (!disposed) timer = window.setTimeout(load, refreshMilliseconds)
      }
    }
    setLoading(true); void load()
    return () => { disposed = true; controller?.abort(); if (timer !== undefined) window.clearTimeout(timer) }
  }, [agentId, refreshKey, refreshMilliseconds])

  return { summary, monitoring, timeline, loading, error, refresh }
}
