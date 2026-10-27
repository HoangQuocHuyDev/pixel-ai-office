import { useEffect, useRef, useState } from 'react'
import { fetchAgentActivities } from '../api/agentClient'
import type { AgentActivity } from '../types'

export type ActivityConnection = 'loading' | 'online' | 'unavailable'

export function useAgentActivities(pollMilliseconds = 2500) {
  const [activities, setActivities] = useState<AgentActivity[]>([])
  const [connection, setConnection] = useState<ActivityConnection>('loading')
  const snapshotRef = useRef('')

  useEffect(() => {
    let disposed = false
    let timer: number | undefined
    let controller: AbortController | undefined
    const poll = async () => {
      controller = new AbortController()
      try {
        const next = await fetchAgentActivities(controller.signal)
        if (disposed) return
        const snapshot = JSON.stringify(next)
        if (snapshot !== snapshotRef.current) { snapshotRef.current = snapshot; setActivities(next) }
        setConnection('online')
      } catch {
        if (!disposed && !controller.signal.aborted) setConnection('unavailable')
      } finally {
        if (!disposed) timer = window.setTimeout(poll, pollMilliseconds)
      }
    }
    void poll()
    return () => { disposed = true; controller?.abort(); if (timer !== undefined) window.clearTimeout(timer) }
  }, [pollMilliseconds])

  return { activities, connection }
}
