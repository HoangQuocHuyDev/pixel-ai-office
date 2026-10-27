import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')
const [app, sidebar, page, hook, client, css] = await Promise.all([
  read('../src/app/App.tsx'), read('../src/components/layout/Sidebar.tsx'),
  read('../src/features/settings/components/SettingsPage.tsx'), read('../src/features/settings/hooks/useSystemStatus.ts'),
  read('../src/features/settings/api/systemClient.ts'), read('../src/styles/global.css'),
])
assert.match(sidebar, /page: 'settings'/); assert.match(app, /<SettingsPage/)
assert.match(page, /Google Gemini|AI Provider/); assert.match(page, /API key/)
assert.doesNotMatch(page, /GEMINI_API_KEY|database_url|password/i)
assert.match(page, /Not tested — no Gemini request was made/); assert.match(page, /Trusted local environment only/)
assert.match(page, /Refresh status/); assert.match(page, /Backend unavailable/)
assert.match(hook, /AbortController/); assert.match(hook, /controller\.abort/); assert.doesNotMatch(hook, /setInterval/)
assert.match(client, /\/api\/v1\/system\/status/); assert.match(css, /\.settings-groups/); assert.match(css, /max-width: 820px/)
console.log('Local settings frontend checks passed')
