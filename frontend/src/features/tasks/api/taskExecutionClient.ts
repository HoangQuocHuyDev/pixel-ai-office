import { API_BASE_URL } from '../../../config/api'
import type { TaskExecution } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { message?: string } } | null
    throw new Error(body?.error?.message ?? `Execution request failed (${response.status}).`)
  }
  return await response.json() as T
}

export function executeTask(taskId: number) {
  return request<TaskExecution>(`/api/v1/tasks/${taskId}/execute`, { method: 'POST' })
}

export function fetchTaskExecutions(taskId: number, signal?: AbortSignal) {
  return request<TaskExecution[]>(`/api/v1/tasks/${taskId}/executions?limit=50&offset=0`, { signal })
}

export function fetchTaskExecution(executionId: number, signal?: AbortSignal) {
  return request<TaskExecution>(`/api/v1/task-executions/${executionId}`, { signal })
}
