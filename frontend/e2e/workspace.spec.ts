import { test, expect } from '@playwright/test'

test.describe('Test F: Workspace & Artifact Viewer', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/agents', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'manager', name: 'Manager AI', role: 'Team Lead', system_prompt: 'Manager prompt', is_active: true },
          { id: 'developer', name: 'Developer AI', role: 'Core Dev', system_prompt: 'Dev prompt', is_active: true },
          { id: 'researcher', name: 'Researcher AI', role: 'Analyst', system_prompt: 'Research prompt', is_active: true },
        ]),
      })
    })

    await page.route('**/api/v1/agents/activities', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    })
  })

  test('displays summary stats, lists artifacts, opens viewer with version history', async ({ page }) => {
    // 1. Mock Summary
    await page.route('**/api/v1/artifacts/summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_artifacts: 3,
          documents: 1,
          code: 1,
          research: 1,
          reports: 0,
        }),
      })
    })

    // 2. Mock List
    await page.route('**/api/v1/artifacts?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 701,
              title: 'API Client Architecture',
              artifact_type: 'code',
              content_format: 'code',
              language: 'typescript',
              agent_id: 'developer',
              agent_name: 'Developer AI',
              task_id: 10,
              task_title: 'Implement API Client',
              workflow_run_id: null,
              workflow_title: null,
              created_at: new Date().toISOString(),
              preview: 'export async function request(path: string) { ... }',
              content_size: 1500,
              current_version_number: 2,
            },
            {
              id: 702,
              title: 'Data Ingestion Analysis',
              artifact_type: 'research',
              content_format: 'markdown',
              language: null,
              agent_id: 'researcher',
              agent_name: 'Researcher AI',
              task_id: 11,
              task_title: 'Analyze Ingestion Streams',
              workflow_run_id: null,
              workflow_title: null,
              created_at: new Date().toISOString(),
              preview: '# Research Analysis\nKey findings on incoming streams...',
              content_size: 2400,
              current_version_number: 1,
            },
          ],
          total: 2,
          limit: 12,
          offset: 0,
        }),
      })
    })

    // 3. Mock Single Artifact
    await page.route('**/api/v1/artifacts/701', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 701,
          title: 'API Client Architecture',
          artifact_type: 'code',
          content_format: 'code',
          language: 'typescript',
          agent_id: 'developer',
          agent_name: 'Developer AI',
          task_id: 10,
          task_title: 'Implement API Client',
          workflow_run_id: null,
          workflow_title: null,
          task_execution_id: 15,
          preview: 'export async function request(path: string) { ... }',
          content_size: 1500,
          content: '```typescript\nexport async function request(path: string): Promise<Response> {\n  return fetch(path)\n}\n```',
          created_at: new Date(Date.now() - 3600000).toISOString(),
          updated_at: new Date().toISOString(),
          current_version_number: 2,
        }),
      })
    })

    // 4. Mock Versions
    await page.route('**/api/v1/artifacts/701/versions*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            { id: 1, artifact_id: 701, version_number: 2, content: '```typescript\nexport async function request(path: string): Promise<Response> {\n  return fetch(path)\n}\n```', content_format: 'code', language: 'typescript', source: 'agent', change_summary: 'Optimized fetch handling', created_at: new Date().toISOString() },
            { id: 2, artifact_id: 701, version_number: 1, content: '```typescript\nfunction request(path) { return fetch(path) }\n```', content_format: 'code', language: 'typescript', source: 'agent', change_summary: 'Initial draft', created_at: new Date(Date.now() - 3600000).toISOString() },
          ],
          total: 2,
          limit: 50,
          offset: 0,
        }),
      })
    })

    await page.goto('/')
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Workspace' }).click()

    // 1. Verify Summary Metrics
    await expect(page.locator('.workspace-summary')).toBeVisible()
    await expect(page.locator('.workspace-summary')).toContainText('Total Artifacts')
    await expect(page.locator('.workspace-summary')).toContainText('3')

    // 2. Verify Artifact List
    const artifactCards = page.locator('.artifact-card')
    await expect(artifactCards).toHaveCount(2)
    await expect(artifactCards.first()).toContainText('API Client Architecture')
    await expect(artifactCards.first()).toContainText('Developer AI')

    // 3. Click to open ArtifactViewer
    await artifactCards.first().click()

    const viewer = page.locator('.artifact-viewer')
    await expect(viewer).toBeVisible()
    await expect(viewer.getByRole('heading', { level: 2 })).toHaveText('API Client Architecture')
    await expect(viewer).toContainText('typescript')
    await expect(viewer).toContainText('Version 2')

    // Close viewer
    await viewer.getByRole('button', { name: 'Close artifact' }).click()
    await expect(viewer).not.toBeVisible()
  })

  test('displays empty workspace state when no artifacts exist', async ({ page }) => {
    await page.route('**/api/v1/artifacts/summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total_artifacts: 0, documents: 0, code: 0, research: 0, reports: 0 }),
      })
    })

    await page.route('**/api/v1/artifacts?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, limit: 12, offset: 0 }),
      })
    })

    await page.goto('/')
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Workspace' }).click()

    await expect(page.locator('.workspace-empty')).toBeVisible()
    await expect(page.locator('.workspace-empty')).toContainText('No artifacts yet')
  })
})
