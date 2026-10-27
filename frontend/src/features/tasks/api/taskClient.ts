import { API_BASE_URL } from '../../../config/api'
import type { AgentId } from '../../agents/types'
import type { OfficeTask, TaskInput, TaskStatus } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { message?: string } } | null
    throw new Error(body?.error?.message ?? `Task request failed (${response.status}).`)
  }
  return response.status === 204 ? undefined as T : await response.json() as T
}

export function fetchTasks(filters: { status?: TaskStatus; agentId?: AgentId }, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: '100', offset: '0' })
  if (filters.status) params.set('status', filters.status)
  if (filters.agentId) params.set('assigned_agent_id', filters.agentId)
  return request<OfficeTask[]>(`/api/v1/tasks?${params}`, { signal })
}
export function createTask(payload: TaskInput) { return request<OfficeTask>('/api/v1/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) }
export function updateTask(id: number, payload: Partial<TaskInput>) { return request<OfficeTask>(`/api/v1/tasks/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) }
export function updateTaskStatus(id: number, status: TaskStatus) { return request<OfficeTask>(`/api/v1/tasks/${id}/status`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) }) }
export function deleteTask(id: number) { return request<void>(`/api/v1/tasks/${id}`, { method: 'DELETE' }) }
