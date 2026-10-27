import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')
const [controls, timeline, client, hook, types, css] = await Promise.all([
  read('../src/features/planning/components/WorkflowControls.tsx'),
  read('../src/features/workflows/components/WorkflowTimeline.tsx'),
  read('../src/features/planning/api/planningClient.ts'),
  read('../src/features/planning/hooks/useWorkflow.ts'),
  read('../src/features/planning/types.ts'),
  read('../src/styles/global.css'),
])

console.log('=== Running TASK 31 Frontend Workflow Recovery Automated Tests ===')

// 1. Client API contract
console.log('Test 1: planningClient exposes retryWorkflow with POST /workflows/{id}/retry')
assert.match(client, /export function retryWorkflow\(workflowId: number, idempotencyKey\?: string\)/)
assert.match(client, /\/api\/v1\/workflows\/\$\{workflowId\}\/retry/)
assert.match(client, /idempotency_key/)
console.log('✓ Passed: retryWorkflow API method exists and targets correct route')

// 2. Hook contract
console.log('Test 2: useWorkflow hook provides retry action and retrying state')
assert.match(hook, /const \[retrying, setRetrying\] = useState\(false\)/)
assert.match(hook, /const retry = async/)
assert.match(hook, /retryWorkflow/)
assert.match(hook, /return {.*retrying.*retry.*}/)
console.log('✓ Passed: useWorkflow exports retry function and state')

// 3. Types contract
console.log('Test 3: WorkflowRun and WorkflowTimelineData types define recovery and lineage properties')
assert.match(types, /can_retry\?: boolean/)
assert.match(types, /retry_block_reason\?: string \| null/)
assert.match(types, /retried_from_run_id\?: number \| null/)
assert.match(types, /retry_run_ids\?: number\[\]/)
assert.match(types, /failed_task_title\?: string \| null/)
assert.match(types, /failed_task_id\?: number \| null/)
console.log('✓ Passed: Lineage and recovery fields present on WorkflowRun')

// 4. WorkflowControls component
console.log('Test 4: WorkflowControls displays Retry button when can_retry is true')
assert.match(controls, /Retry Workflow/)
assert.match(controls, /isFailed && run\.can_retry/)
assert.match(controls, /confirm\(/)
assert.match(controls, /Retrying\.\.\./)
assert.match(controls, /workflow-failed-task/)
assert.match(controls, /workflow-retry-blocked/)
assert.match(controls, /workflow-lineage-tag/)
assert.match(controls, /Retried from Run #/)
console.log('✓ Passed: WorkflowControls handles failure, lineage, and retry confirmations')

// 5. WorkflowTimeline component
console.log('Test 5: WorkflowTimeline displays lineage tags and inline retry trigger')
assert.match(timeline, /Retried from Run #/)
assert.match(timeline, /Retried in Run #/)
assert.match(timeline, /workflow-failed-task/)
assert.match(timeline, /data\.failed_task_title/)
assert.match(timeline, /workflow-timeline__error-banner/)
assert.match(timeline, /workflow-retry-inline-btn/)
assert.match(timeline, /onRetryRun/)
console.log('✓ Passed: WorkflowTimeline exposes failure details and retry lineage')

// 6. CSS styling
console.log('Test 6: CSS styles defined for lineage, failed tasks, and retry elements')
assert.match(css, /\.workflow-lineage-tag/)
assert.match(css, /\.workflow-retry-button/)
assert.match(css, /\.workflow-failed-task/)
assert.match(css, /\.workflow-timeline__error-banner/)
console.log('✓ Passed: Styles exist in global.css')

console.log('=== ALL TASK 31 FRONTEND TESTS PASSED SUCCESSFULLY! ===')

