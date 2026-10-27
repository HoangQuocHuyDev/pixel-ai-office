import type { AgentId } from '../agents/types'
import type { OfficeTask, TaskPriority } from '../tasks/types'

export type PlannedTask = {
  title: string
  description: string
  priority: TaskPriority
  assigned_agent_id: Extract<AgentId, 'developer' | 'researcher'>
  sequence_order: number
}

export type PlanProposal = { title: string; objective: string; tasks: PlannedTask[] }
export type PlanSummary = {
  id: number
  title: string
  objective: string
  status: 'draft' | 'approved' | 'cancelled'
  source_conversation_id: number | null
  created_at: string
  updated_at: string
}
export type ApprovedPlan = PlanSummary & { tasks: OfficeTask[] }
export type WorkflowStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
export type WorkflowRun = {
  id: number; plan_id: number; status: WorkflowStatus
  current_task_id: number | null; current_task_title: string | null; current_agent_id: string | null
  completed_tasks: number; total_tasks: number; final_report: string | null
  error_code: string | null; error_message: string | null
  started_at: string; completed_at: string | null; updated_at: string
  can_retry?: boolean
  retry_block_reason?: string | null
  retried_from_run_id?: number | null
  retry_run_ids?: number[]
  failed_task_title?: string | null
  failed_task_id?: number | null
}
