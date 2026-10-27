import { API_BASE_URL } from '../../../config/api'
import type { AgentActivity, AgentMetadata, AgentMonitoring, AgentTimeline, MonitoringSummary } from '../types'

export async function fetchAgents(signal?: AbortSignal): Promise<AgentMetadata[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/agents`, { signal })
  if (!response.ok) {
    throw new Error(`Unable to load agents (${response.status}).`)
  }
  return (await response.json()) as AgentMetadata[]
}


export async function fetchAgentActivities(signal?: AbortSignal): Promise<AgentActivity[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/agents/activities`, { signal })
  if (!response.ok) throw new Error(`Unable to load agent activities (${response.status}).`)
  return (await response.json()) as AgentActivity[]
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal })
  if (!response.ok) throw new Error(`Unable to load monitoring data (${response.status}).`)
  return (await response.json()) as T
}

export const fetchMonitoringSummary = (signal?: AbortSignal) =>
  getJson<MonitoringSummary>('/api/v1/agents/monitoring/summary', signal)
export const fetchAgentMonitoring = (agentId: AgentMetadata['id'], signal?: AbortSignal) =>
  getJson<AgentMonitoring>(`/api/v1/agents/${agentId}/monitoring`, signal)
export const fetchAgentTimeline = (agentId: AgentMetadata['id'], offset = 0, signal?: AbortSignal) =>
  getJson<AgentTimeline>(`/api/v1/agents/${agentId}/timeline?limit=25&offset=${offset}`, signal)
