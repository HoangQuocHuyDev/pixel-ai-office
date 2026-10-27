export type AgentId = 'manager' | 'developer' | 'researcher'

export type AgentRole = AgentId

export type AgentMetadata = {
  id: AgentId
  name: string
  role: AgentRole
  description: string
  responsibilities: string[]
}

export type AgentActivityStatus = 'idle' | 'working' | 'failed'
export type AgentActivity = {
  agent_id: AgentId
  status: AgentActivityStatus
  current_task_id: number | null
  current_task_title: string | null
  workflow_run_id: number | null
  activity_type: string | null
  updated_at: string
}

export type AgentStatistics = {
  total_executions: number; completed_executions: number; failed_executions: number
  cancelled_executions: number; success_rate: number | null
  average_duration_seconds: number | null; last_active_at: string | null
}
export type AgentExecution = {
  id: number; task_id: number; task_title: string; workflow_run_id: number | null
  status: 'running' | 'completed' | 'failed' | 'cancelled'; started_at: string
  completed_at: string | null; duration_seconds: number | null; output_content: string | null
  error_code: string | null; error_message: string | null
}
export type AgentMonitoring = {
  agent: AgentMetadata; current_activity: AgentActivity
  current_task: { id: number; title: string; status: string } | null
  current_workflow: { id: number; plan_id: number; plan_title: string; status: string } | null
  statistics: AgentStatistics; recent_executions: AgentExecution[]
}
export type AgentTimelineEvent = {
  event_id: string; event_type: string; agent_id: AgentId; task_id: number | null
  workflow_run_id: number | null; execution_id: number | null; status: string
  timestamp: string; description: string
}
export type AgentTimeline = { items: AgentTimelineEvent[]; total: number; limit: number; offset: number }
export type MonitoringSummary = {
  total_agents: number; working_agents: number; idle_agents: number; failed_agents: number
  total_executions: number; completed_executions: number; failed_executions: number; active_workflows: number
}
