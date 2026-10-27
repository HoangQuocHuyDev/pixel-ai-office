import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const files = {
  app: await readFile(new URL('../src/app/App.tsx', import.meta.url), 'utf8'),
  sidebar: await readFile(new URL('../src/components/layout/Sidebar.tsx', import.meta.url), 'utf8'),
  page: await readFile(new URL('../src/features/tasks/components/TasksPage.tsx', import.meta.url), 'utf8'),
  hook: await readFile(new URL('../src/features/tasks/hooks/useTasks.ts', import.meta.url), 'utf8'),
  client: await readFile(new URL('../src/features/tasks/api/taskClient.ts', import.meta.url), 'utf8'),
}

assert.match(files.sidebar, /page: 'tasks'/)
assert.match(files.app, /activePage === 'tasks'/)
assert.match(files.page, /Create Task/)
assert.match(files.page, /Edit Task/)
assert.match(files.page, /Delete/)
assert.match(files.page, /All statuses/)
assert.match(files.page, /All agents/)
for (const status of ['todo', 'in_progress', 'done', 'cancelled']) assert.match(files.page, new RegExp(status))
for (const method of ['createTask', 'updateTask', 'updateTaskStatus', 'deleteTask']) assert.match(files.hook, new RegExp(method))
assert.match(files.client, /assigned_agent_id/)
assert.match(files.client, /\/api\/v1\/tasks/)

console.log('Task management frontend contract checks passed.')
