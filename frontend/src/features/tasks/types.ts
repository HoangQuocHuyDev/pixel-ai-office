import type { AgentId } from '../agents/types'

export type TaskStatus = 'todo' | 'in_progress' | 'done' | 'cancelled'
export type TaskPriority = 'low' | 'medium' | 'high'
export type OfficeTask = {
  id: number; title: string; description: string | null; status: TaskStatus
  priority: TaskPriority; assigned_agent_id: AgentId | null
  plan_id: number | null; sequence_order: number | null
  created_at: string; updated_at: string; completed_at: string | null
}
export type TaskInput = Pick<OfficeTask, 'title' | 'description' | 'status' | 'priority' | 'assigned_agent_id'>
export type ExecutionStatus = 'running' | 'completed' | 'failed' | 'cancelled'
export type TaskExecution = {
  id: number; task_id: number; agent_id: AgentId; status: ExecutionStatus
  input_snapshot: string; output_content: string | null
  error_code: string | null; error_message: string | null
  started_at: string; completed_at: string | null; created_at: string
}
