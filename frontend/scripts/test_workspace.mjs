import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')
const [app, sidebar, page, viewer, editor, history, diff, hook, versionsHook, client, css] = await Promise.all([
  read('../src/app/App.tsx'), read('../src/components/layout/Sidebar.tsx'),
  read('../src/features/workspace/components/WorkspacePage.tsx'), read('../src/features/workspace/components/ArtifactViewer.tsx'),
  read('../src/features/workspace/components/ArtifactEditor.tsx'), read('../src/features/workspace/components/ArtifactVersionHistory.tsx'), read('../src/features/workspace/components/ArtifactDiffViewer.tsx'),
  read('../src/features/workspace/hooks/useArtifacts.ts'), read('../src/features/workspace/hooks/useArtifactVersions.ts'), read('../src/features/workspace/api/artifactClient.ts'), read('../src/styles/global.css'),
])
assert.match(sidebar, /page: 'workspace'/); assert.match(app, /<WorkspaceArtifactsPage/)
assert.match(page, /Browse AI-generated documents, code and reports/); assert.match(page, /Search artifact titles/)
assert.match(page, /Previous/); assert.match(page, /No artifacts yet/)
assert.match(viewer, /navigator\.clipboard\.writeText/); assert.match(viewer, /Download current version/)
assert.doesNotMatch(viewer, /dangerouslySetInnerHTML/); assert.match(viewer, /MAX_RENDER_CHARS/)
assert.match(viewer, /Discard unsaved changes/); assert.match(viewer, /Version History/)
assert.match(editor, /Save Version/); assert.match(editor, /expected_version_number/); assert.match(editor, /status === 409/)
assert.match(history, /Restore as new version/); assert.match(history, /confirm\(/); assert.match(history, /Download version/)
assert.match(diff, /unified_diff/); assert.doesNotMatch(diff, /dangerouslySetInnerHTML/)
assert.match(hook, /AbortController/); assert.match(hook, /clearTimeout/); assert.match(hook, /350/)
assert.match(versionsHook, /AbortController/)
assert.doesNotMatch(hook, /setInterval/); assert.match(client, /URLSearchParams/); assert.match(client, /\/download/)
assert.match(css, /\.artifact-list/); assert.match(css, /@media \(max-width: 560px\)/)
console.log('Workspace artifact frontend checks passed')
