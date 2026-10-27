import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')
const [page, client, types] = await Promise.all([
  read('../src/features/tasks/components/TasksPage.tsx'),
  read('../src/features/tasks/api/taskExecutionClient.ts'),
  read('../src/features/tasks/types.ts'),
])

assert.match(page, /Run Task/)
assert.match(page, /Agent is working/)
assert.match(page, /Retry Task/)
assert.match(page, /Execution History/)
assert.match(page, /execution\.output_content/)
assert.match(page, /<pre>/)
assert.doesNotMatch(page, /dangerouslySetInnerHTML/)
assert.match(page, /if \(runningTaskId !== null\) return/)
assert.match(page, /fetchTaskExecutions\(viewing\.id/)
assert.match(page, /Check execution history for the persisted state/)
assert.match(client, /\/api\/v1\/tasks\/\$\{taskId\}\/execute/)
assert.match(client, /\/api\/v1\/tasks\/\$\{taskId\}\/executions/)
assert.match(client, /\/api\/v1\/task-executions\/\$\{executionId\}/)
assert.match(types, /'running' \| 'completed' \| 'failed' \| 'cancelled'/)

console.log('Task execution frontend contract checks passed.')
