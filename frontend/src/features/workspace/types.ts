import type { AgentId } from '../agents/types'

export type ArtifactType = 'document' | 'code' | 'research' | 'report'
export type ContentFormat = 'plain_text' | 'markdown' | 'json' | 'code'
export type ArtifactItem = {
  id: number; title: string; artifact_type: ArtifactType; content_format: ContentFormat
  language: string | null; agent_id: AgentId | null; agent_name: string | null
  task_id: number | null; task_title: string | null; workflow_run_id: number | null
  workflow_title: string | null; created_at: string; preview: string; content_size: number
  current_version_number: number
}
export type ArtifactDetail = ArtifactItem & { task_execution_id: number | null; content: string; updated_at: string }
export type ArtifactList = { items: ArtifactItem[]; total: number; limit: number; offset: number }
export type ArtifactSummary = { total_artifacts: number; documents: number; code: number; research: number; reports: number }
export type ArtifactFilters = { search: string; artifactType: ArtifactType | ''; agentId: AgentId | ''; offset: number }
export type ArtifactVersionItem = {
  id: number; version_number: number; source: 'agent' | 'user' | 'restore' | 'backfill'
  change_summary: string | null; restored_from_version_id: number | null
  restored_from_version_number: number | null; created_at: string; content_size: number
}
export type ArtifactVersionDetail = ArtifactVersionItem & {
  artifact_id: number; content: string; content_format: ContentFormat; language: string | null
}
export type ArtifactVersionList = { items: ArtifactVersionItem[]; total: number; limit: number; offset: number; current_version_number: number }
export type ArtifactCompare = { artifact_id: number; from_version: number; to_version: number; unified_diff: string; added_lines: number; removed_lines: number }
export type SaveVersionInput = { content: string; content_format: ContentFormat; language: string | null; change_summary: string | null; expected_version_number: number }
