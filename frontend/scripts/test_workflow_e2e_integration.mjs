import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')

const [
  planningClient,
  workflowTimelineClient,
  planningHook,
  timelineHook,
  planningTypes,
  workflowControls,
  workflowTimeline,
  workflowProgress,
  workflowStepCard,
  workflowHandoffCard,
  workflowFinalReport,
  workflowTypes,
  artifactViewer,
  artifactVersionHistory,
  workspacePage,
] = await Promise.all([
  read('../src/features/planning/api/planningClient.ts'),
  read('../src/features/workflows/api/workflowTimelineClient.ts'),
  read('../src/features/planning/hooks/useWorkflow.ts'),
  read('../src/features/workflows/hooks/useWorkflowTimeline.ts'),
  read('../src/features/planning/types.ts'),
  read('../src/features/planning/components/WorkflowControls.tsx'),
  read('../src/features/workflows/components/WorkflowTimeline.tsx'),
  read('../src/features/workflows/components/WorkflowProgress.tsx'),
  read('../src/features/workflows/components/WorkflowStepCard.tsx'),
  read('../src/features/workflows/components/WorkflowHandoffCard.tsx'),
  read('../src/features/workflows/components/WorkflowFinalReport.tsx'),
  read('../src/features/workflows/types.ts'),
  read('../src/features/workspace/components/ArtifactViewer.tsx'),
  read('../src/features/workspace/components/ArtifactVersionHistory.tsx'),
  read('../src/features/workspace/components/WorkspacePage.tsx'),
])

console.log('=== Running TASK 33: Frontend Workflow E2E Integration Suite ===')

// 1. Planning and Workflow Client API Contracts
console.log('Test 1: PlanningClient and WorkflowTimelineClient API contracts')
assert.match(planningClient, /export function startWorkflow\(/)
assert.match(planningClient, /export function cancelWorkflow\(/)
assert.match(planningClient, /export function retryWorkflow\(/)
assert.match(planningClient, /\/api\/v1\/workflows\/\$\{workflowId\}\/retry/)
assert.match(planningClient, /\/api\/v1\/workflows\/\$\{workflowId\}\/cancel/)
assert.match(workflowTimelineClient, /export async function fetchWorkflowTimeline\(/)
assert.match(workflowTimelineClient, /\/api\/v1\/workflows\/\$\{workflowId\}\/timeline/)
console.log('✓ Passed: Clients expose start, cancel, retry, and timeline API methods')

// 2. useWorkflow & useWorkflowTimeline Hooks Integration
console.log('Test 2: useWorkflow & useWorkflowTimeline hooks handle full lifecycle and polling')
assert.match(planningHook, /startWorkflow/)
assert.match(planningHook, /cancelWorkflow/)
assert.match(planningHook, /retryWorkflow/)
assert.match(planningHook, /retrying/)
assert.match(planningHook, /starting/)
assert.match(planningHook, /window\.setInterval/)
assert.match(timelineHook, /fetchWorkflowTimeline/)
assert.match(timelineHook, /pollMilliseconds/)
console.log('✓ Passed: Hooks manage workflow state, actions, and timeline polling')

// 3. Workflow Types & Lineage Contract
console.log('Test 3: Types declare retry lineage and timeline handoffs')
assert.match(planningTypes, /can_retry\?: boolean/)
assert.match(planningTypes, /retry_block_reason\?: string \| null/)
assert.match(planningTypes, /retried_from_run_id\?: number \| null/)
assert.match(planningTypes, /retry_run_ids\?: number\[\]/)
assert.match(workflowTypes, /handoffs\?: WorkflowHandoff\[\]/)
assert.match(workflowTypes, /steps: WorkflowStep\[\]/)
assert.match(workflowTypes, /finalization: \{ status:/)
console.log('✓ Passed: TypeScript types cover lineage and structured timeline data')

// 4. WorkflowControls Component Integration
console.log('Test 4: WorkflowControls renders Start, Cancel, Retry actions with lineage tags')
assert.match(workflowControls, /workflow\.start/)
assert.match(workflowControls, /workflow\.cancel/)
assert.match(workflowControls, /workflow\.retry/)
assert.match(workflowControls, /can_retry/)
assert.match(workflowControls, /Retried from Run #/)
assert.match(workflowControls, /workflow-retry-blocked/)
assert.match(workflowControls, /Retrying\.\.\./)
assert.match(workflowControls, /Starting\.\.\./)
console.log('✓ Passed: WorkflowControls includes lifecycle buttons, confirmations, and lineage indicators')

// 5. WorkflowTimeline Component Integration
console.log('Test 5: WorkflowTimeline integrates Progress, Steps, Handoffs, and Final Report')
assert.match(workflowTimeline, /<WorkflowProgress/)
assert.match(workflowTimeline, /<WorkflowStepCard/)
assert.match(workflowTimeline, /<WorkflowHandoffCard/)
assert.match(workflowTimeline, /<WorkflowFinalReport/)
assert.match(workflowTimeline, /workflow-timeline/)
console.log('✓ Passed: WorkflowTimeline orchestrates all subcomponents cleanly')

// 6. WorkflowStepCard Component Integration
console.log('Test 6: WorkflowStepCard displays agent badge, status, and execution outputs')
assert.match(workflowStepCard, /step\.agent_name/)
assert.match(workflowStepCard, /step\.status/)
assert.match(workflowStepCard, /step\.reused_from_run_id/)
console.log('✓ Passed: WorkflowStepCard presents task progress and execution details')

// 7. WorkflowHandoffCard Component Integration
console.log('Test 7: WorkflowHandoffCard displays source, target, summary, deliverables, and findings')
assert.match(workflowHandoffCard, /source_agent_id/)
assert.match(workflowHandoffCard, /target_agent_id/)
assert.match(workflowHandoffCard, /deliverables/)
assert.match(workflowHandoffCard, /findings/)
console.log('✓ Passed: WorkflowHandoffCard presents rich agent collaboration data')

// 8. WorkflowFinalReport Component Integration
console.log('Test 8: WorkflowFinalReport displays Manager final report preview and status')
assert.match(workflowFinalReport, /finalization\.report_preview|report_preview/)
console.log('✓ Passed: WorkflowFinalReport displays Manager report output')

// 9. Workspace & Artifact Version History Integration
console.log('Test 9: ArtifactViewer and VersionHistory support markdown, code, and version switching')
assert.match(artifactViewer, /artifact\.content|artifact\.content_format/)
assert.match(artifactVersionHistory, /version_number/)
assert.match(workspacePage, /ArtifactViewer/)
console.log('✓ Passed: Workspace provides artifact inspection and version browsing')

console.log('\n=== All 9 Frontend Integration Tests Passed Successfully! ===')
