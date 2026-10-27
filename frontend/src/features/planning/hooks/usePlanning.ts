import { useCallback, useEffect, useRef, useState } from 'react'
import { approvePlan, fetchPlan, fetchPlans, generatePlan } from '../api/planningClient'
import type { ApprovedPlan, PlanProposal, PlanSummary } from '../types'

function newIdempotencyKey() {
  return crypto.randomUUID().replaceAll('-', '')
}

export function usePlanning(onApproved: () => void | Promise<void>) {
  const [proposal, setProposal] = useState<PlanProposal | null>(null)
  const [plans, setPlans] = useState<PlanSummary[]>([])
  const [selectedPlan, setSelectedPlan] = useState<ApprovedPlan | null>(null)
  const [generating, setGenerating] = useState(false)
  const [approving, setApproving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const keyRef = useRef(newIdempotencyKey())

  const loadPlans = useCallback(async (signal?: AbortSignal) => {
    try { setPlans(await fetchPlans(signal)) }
    catch (reason) { if (!signal?.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load plans.') }
  }, [])

  useEffect(() => { const controller = new AbortController(); void loadPlans(controller.signal); return () => controller.abort() }, [loadPlans])

  const generate = async (objective: string) => {
    setGenerating(true); setError(null); keyRef.current = newIdempotencyKey()
    try { setProposal(await generatePlan(objective)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to generate plan.') }
    finally { setGenerating(false) }
  }
  const approve = async () => {
    if (!proposal || approving) return
    setApproving(true); setError(null)
    try {
      const approved = await approvePlan(proposal, keyRef.current)
      setProposal(null); setSelectedPlan(approved)
      await Promise.all([loadPlans(), onApproved()])
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to approve plan.') }
    finally { setApproving(false) }
  }
  const cancel = () => { setProposal(null); setError(null); keyRef.current = newIdempotencyKey() }
  const selectPlan = async (id: number) => {
    setError(null)
    try { setSelectedPlan(await fetchPlan(id)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load plan.') }
  }
  return { proposal, plans, selectedPlan, generating, approving, error, generate, approve, cancel, selectPlan, setSelectedPlan }
}
