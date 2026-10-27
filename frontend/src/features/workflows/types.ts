import type { AgentId } from '../agents/types'
import type { WorkflowStatus } from '../planning/types'

export type WorkflowArtifactReference = { id: number; title: string; artifact_type: string; agent_id: AgentId | null; task_execution_id: number | null; workflow_run_id: number | null; created_at: string }
export type WorkflowAttempt = { id: number; attempt_number: number; status: 'running' | 'completed' | 'failed' | 'cancelled'; started_at: string; completed_at: string | null; duration_seconds: number | null; result_preview: string | null; result_truncated: boolean; error_code: string | null; error_message: string | null; artifacts: WorkflowArtifactReference[] }
export type WorkflowStep = { step_number: number; task_id: number; task_title: string; task_description: string | null; agent_id: AgentId | null; agent_name: string | null; status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'; started_at: string | null; completed_at: string | null; duration_seconds: number | null; attempts: WorkflowAttempt[]; pre_existing?: boolean; reused_from_run_id?: number | null; reused_execution_id?: number | null }
export type WorkflowHandoff = {
  id: number
  workflow_run_id: number
  source_task_execution_id: number
  source_task_id: number
  source_task_title: string
  source_agent_id: AgentId | string
  source_agent_name: string | null
  target_task_id: number
  target_task_title: string
  target_agent_id: AgentId | string
  target_agent_name: string | null
  summary: string
  key_findings: string[]
  deliverables: string[]
  next_steps: string | null
  artifacts: WorkflowArtifactReference[]
  created_at: string
}
export type WorkflowTimelineData = {
  workflow_id: number; status: WorkflowStatus
  plan: { id: number; title: string; objective: string; status: string; created_at: string; approval_timestamp_available: boolean }
  started_at: string; completed_at: string | null; updated_at: string
  progress: { total_tasks: number; completed_tasks: number; running_tasks: number; pending_tasks: number; failed_tasks: number; cancelled_tasks: number; progress_percentage: number }
  steps: WorkflowStep[]
  handoffs?: WorkflowHandoff[]
  finalization: { status: 'not_started' | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'; started_at: string | null; completed_at: string | null; report_preview: string | null; report_truncated: boolean; error_code: string | null; error_message: string | null; artifacts: WorkflowArtifactReference[] }
  error_code: string | null; error_message: string | null; execution_scope_note: string
  can_retry?: boolean
  retry_block_reason?: string | null
  retried_from_run_id?: number | null
  retry_run_ids?: number[]
  failed_task_title?: string | null
  failed_task_id?: number | null
}
