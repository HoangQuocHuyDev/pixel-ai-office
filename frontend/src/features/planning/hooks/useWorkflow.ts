import { useCallback, useEffect, useRef, useState } from 'react'
import { cancelWorkflow, fetchWorkflow, fetchWorkflows, retryWorkflow, startWorkflow } from '../api/planningClient'
import type { WorkflowRun } from '../types'

const active = (run: WorkflowRun | null) => run?.status === 'pending' || run?.status === 'running'

export function useWorkflow(planId: number, onTerminal: () => void | Promise<void>) {
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [history, setHistory] = useState<WorkflowRun[]>([])
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const notifiedRef = useRef<number | null>(null)

  const loadHistory = useCallback(async (signal?: AbortSignal) => {
    try { const runs = await fetchWorkflows(planId, signal); setHistory(runs); setRun(runs[0] ?? null) }
    catch (reason) { if (!signal?.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load workflows.') }
    finally { if (!signal?.aborted) setLoading(false) }
  }, [planId])
  useEffect(() => { const controller = new AbortController(); void loadHistory(controller.signal); return () => controller.abort() }, [loadHistory])
  useEffect(() => {
    const runId = run?.id
    if (!active(run) || runId === undefined) return
    const controller = new AbortController()
    const timer = window.setInterval(() => { void fetchWorkflow(runId, controller.signal).then((next) => {
      setRun(next); setHistory((items) => [next, ...items.filter((item) => item.id !== next.id)])
      if (!active(next) && notifiedRef.current !== next.id) { notifiedRef.current = next.id; void onTerminal() }
    }).catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Workflow status polling failed.') }) }, 3000)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [run?.id, run?.status, onTerminal])
  const start = async () => {
    if (starting || active(run)) return
    setStarting(true); setError(null)
    try { const created = await startWorkflow(planId, crypto.randomUUID().replaceAll('-', '')); setRun(created); setHistory((items) => [created, ...items]); notifiedRef.current = null }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to start workflow.') }
    finally { setStarting(false) }
  }
  const retry = async (targetRunId?: number) => {
    const idToRetry = targetRunId ?? run?.id
    if (!idToRetry || retrying || active(run)) return
    setRetrying(true); setError(null)
    try {
      const created = await retryWorkflow(idToRetry)
      setRun(created)
      setHistory((items) => [created, ...items.filter((item) => item.id !== created.id)])
      notifiedRef.current = null
      return created
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to retry workflow.')
    } finally {
      setRetrying(false)
    }
  }
  const cancel = async () => { if (!run || !active(run)) return; try { const next = await cancelWorkflow(run.id); setRun(next); await onTerminal() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to cancel workflow.') } }
  return { run, history, loading, starting, retrying, error, start, retry, cancel }
}
