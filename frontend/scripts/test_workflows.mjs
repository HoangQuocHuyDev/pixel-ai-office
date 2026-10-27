import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')
const [component, hook, client, panel] = await Promise.all([
  read('../src/features/planning/components/WorkflowControls.tsx'),
  read('../src/features/planning/hooks/useWorkflow.ts'),
  read('../src/features/planning/api/planningClient.ts'),
  read('../src/features/planning/components/PlanningPanel.tsx'),
])

assert.match(component, /Start Workflow/)
assert.match(component, /Cancel Workflow/)
assert.match(component, /Manager Final Report/)
assert.match(component, /completed_tasks/)
assert.match(component, /current_agent_id/)
assert.match(hook, /setInterval/)
assert.match(hook, /3000/)
assert.match(hook, /clearInterval/)
assert.match(hook, /if \(starting \|\| active\(run\)\) return/)
assert.match(client, /\/api\/v1\/plans\/\$\{planId\}\/workflows/)
assert.match(client, /\/api\/v1\/workflows\/\$\{workflowId\}/)
assert.match(panel, /<WorkflowControls/)
assert.doesNotMatch(component, /dangerouslySetInnerHTML/)

console.log('Workflow frontend contract checks passed.')
