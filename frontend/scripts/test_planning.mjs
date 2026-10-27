import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')
const [panel, hook, client, types, tasks] = await Promise.all([
  read('../src/features/planning/components/PlanningPanel.tsx'),
  read('../src/features/planning/hooks/usePlanning.ts'),
  read('../src/features/planning/api/planningClient.ts'),
  read('../src/features/planning/types.ts'),
  read('../src/features/tasks/components/TasksPage.tsx'),
])

assert.match(panel, /Generate Plan/)
assert.match(panel, /Manager is analyzing/)
assert.match(panel, /Approve Plan/)
assert.match(panel, /Cancel/)
assert.match(panel, /Regenerate Plan/)
assert.match(panel, /regular Manager chat/)
assert.match(panel, /planning\.error/)
assert.match(panel, /planning\.approving/)
assert.match(hook, /if \(!proposal \|\| approving\) return/)
assert.match(hook, /Promise\.all\(\[loadPlans\(\), onApproved\(\)\]\)/)
assert.match(client, /\/api\/v1\/planning\/generate/)
assert.match(client, /\/api\/v1\/planning\/approve/)
assert.match(client, /\/api\/v1\/plans/)
assert.match(types, /'developer' \| 'researcher'/)
assert.match(tasks, /<PlanningPanel onApproved=\{state\.load\}/)

console.log('Manager planning frontend contract checks passed.')
