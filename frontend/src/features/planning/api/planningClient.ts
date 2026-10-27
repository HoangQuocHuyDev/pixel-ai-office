import { API_BASE_URL } from '../../../config/api'
import type { ApprovedPlan, PlanProposal, PlanSummary, WorkflowRun } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { message?: string } } | null
    throw new Error(body?.error?.message ?? `Planning request failed (${response.status}).`)
  }
  return await response.json() as T
}

export function generatePlan(objective: string, signal?: AbortSignal) {
  return request<PlanProposal>('/api/v1/planning/generate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ objective }), signal,
  })
}

export function approvePlan(proposal: PlanProposal, idempotencyKey: string) {
  return request<ApprovedPlan>('/api/v1/planning/approve', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ proposal, idempotency_key: idempotencyKey }),
  })
}

export function fetchPlans(signal?: AbortSignal) {
  return request<PlanSummary[]>('/api/v1/plans?limit=50&offset=0', { signal })
}

export function fetchPlan(id: number, signal?: AbortSignal) {
  return request<ApprovedPlan>(`/api/v1/plans/${id}`, { signal })
}

export function startWorkflow(planId: number, idempotencyKey: string) {
  return request<WorkflowRun>(`/api/v1/plans/${planId}/workflows`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idempotency_key: idempotencyKey }) })
}

export function fetchWorkflows(planId: number, signal?: AbortSignal) {
  return request<WorkflowRun[]>(`/api/v1/plans/${planId}/workflows?limit=50&offset=0`, { signal })
}

export function fetchWorkflow(workflowId: number, signal?: AbortSignal) {
  return request<WorkflowRun>(`/api/v1/workflows/${workflowId}`, { signal })
}

export function cancelWorkflow(workflowId: number) {
  return request<WorkflowRun>(`/api/v1/workflows/${workflowId}/cancel`, { method: 'POST' })
}

export function retryWorkflow(workflowId: number, idempotencyKey?: string) {
  return request<WorkflowRun>(`/api/v1/workflows/${workflowId}/retry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idempotency_key: idempotencyKey ?? crypto.randomUUID().replaceAll('-', '') }),
  })
}
