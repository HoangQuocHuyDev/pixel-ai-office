import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
const read = path => readFile(new URL(path, import.meta.url), 'utf8')
const [controls, timeline, step, progress, report, hook, client, app, workspace, css, types, handoffCard] = await Promise.all([
  read('../src/features/planning/components/WorkflowControls.tsx'), read('../src/features/workflows/components/WorkflowTimeline.tsx'),
  read('../src/features/workflows/components/WorkflowStepCard.tsx'), read('../src/features/workflows/components/WorkflowProgress.tsx'),
  read('../src/features/workflows/components/WorkflowFinalReport.tsx'), read('../src/features/workflows/hooks/useWorkflowTimeline.ts'),
  read('../src/features/workflows/api/workflowTimelineClient.ts'), read('../src/app/App.tsx'),
  read('../src/features/workspace/components/WorkspacePage.tsx'), read('../src/styles/global.css'),
  read('../src/features/workflows/types.ts'), read('../src/features/workflows/components/WorkflowHandoffCard.tsx'),
])
assert.match(controls, /View Execution Timeline/); assert.match(controls, /Previous runs/)
assert.match(timeline, /Execution Timeline|execution timeline/); assert.match(timeline, /WorkflowProgress/)
assert.match(step, /execution attempt/); assert.match(step, /result_preview/); assert.match(step, /Open artifact/)
assert.match(step, /pre_existing/); assert.match(step, /Completed prior to this workflow run/)
assert.match(types, /pre_existing\?: boolean/)
assert.match(types, /export type WorkflowHandoff = {/)
assert.match(types, /handoffs\?: WorkflowHandoff\[\]/)
assert.match(progress, /progress_percentage/); assert.match(report, /Final Report/); assert.match(report, /Open report artifact/)
assert.match(hook, /2500/); assert.match(hook, /AbortController/); assert.match(hook, /clearTimeout/); assert.match(hook, /visibilityState/); assert.doesNotMatch(hook, /setInterval/)
assert.match(client, /\/timeline/); assert.match(app, /workspaceArtifactId/); assert.match(workspace, /initialArtifactId/)
assert.match(css, /\.workflow-timeline/); assert.match(css, /max-width: 560px/)
assert.match(timeline, /WorkflowHandoffCard/)
assert.match(handoffCard, /timeline-handoff/)
assert.match(handoffCard, /key_findings/)
assert.match(handoffCard, /deliverables/)
assert.match(handoffCard, /onOpenArtifact/)
assert.match(css, /\.timeline-handoff/)
assert.doesNotMatch(timeline + step + report + handoffCard, /dangerouslySetInnerHTML/)
console.log('Workflow timeline frontend checks passed')
