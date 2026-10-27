import { API_BASE_URL } from '../../../config/api'
import type { WorkflowTimelineData } from '../types'

export async function fetchWorkflowTimeline(workflowId: number, signal?: AbortSignal): Promise<WorkflowTimelineData> {
  const response = await fetch(`${API_BASE_URL}/api/v1/workflows/${workflowId}/timeline`, { signal })
  if (!response.ok) throw new Error(`Unable to load workflow timeline (${response.status}).`)
  return (await response.json()) as WorkflowTimelineData
}
