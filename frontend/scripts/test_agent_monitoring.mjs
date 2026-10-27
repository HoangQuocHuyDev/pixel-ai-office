import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')
const [app, sidebar, page, hook, client, css] = await Promise.all([
  read('../src/app/App.tsx'), read('../src/components/layout/Sidebar.tsx'),
  read('../src/features/agents/components/AgentsPage.tsx'),
  read('../src/features/agents/hooks/useAgentMonitoring.ts'),
  read('../src/features/agents/api/agentClient.ts'), read('../src/styles/global.css'),
])
assert.match(sidebar, /page: 'agents'/)
assert.match(app, /<AgentsPage/)
assert.match(page, /Agent Monitoring/)
assert.match(page, /Monitoring summary/)
assert.match(page, /Execution History/)
assert.match(page, /Activity Timeline/)
assert.match(page, /Execution Result/)
assert.doesNotMatch(page, /dangerouslySetInnerHTML/)
assert.match(hook, /AbortController/)
assert.match(hook, /clearTimeout/)
assert.match(hook, /setTimeout\(load, refreshMilliseconds\)/)
assert.match(client, /monitoring\/summary/)
assert.match(client, /timeline\?limit=25&offset=/)
assert.match(css, /@media \(max-width: 900px\)/)
assert.match(css, /@media \(max-width: 560px\)/)
console.log('Agent monitoring frontend checks passed')
