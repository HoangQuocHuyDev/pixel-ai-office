import { test, expect } from '@playwright/test'

test.describe('Test A: Application Smoke & Navigation', () => {
  test('renders main office page without errors and navigates cleanly', async ({ page }) => {
    const pageErrors: Error[] = []
    page.on('pageerror', (err) => pageErrors.push(err))

    // Mock initial API routes to keep test fully isolated
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
        body: JSON.stringify([
          { agent_id: 'manager', status: 'idle', current_task_id: null, current_task_title: null, workflow_run_id: null, updated_at: new Date().toISOString() },
          { agent_id: 'developer', status: 'idle', current_task_id: null, current_task_title: null, workflow_run_id: null, updated_at: new Date().toISOString() },
          { agent_id: 'researcher', status: 'idle', current_task_id: null, current_task_title: null, workflow_run_id: null, updated_at: new Date().toISOString() },
        ]),
      })
    })

    await page.route('**/api/v1/conversations*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    })

    await page.goto('/')

    // 1. Verify Header and Eyebrow
    await expect(page.locator('.app-header')).toBeVisible()
    await expect(page.locator('#workspace-title')).toHaveText('Your AI Workspace')

    // 2. Verify Sidebar is visible on desktop
    const sidebar = page.locator('#workspace-sidebar')
    await expect(sidebar).toBeVisible()

    // 3. Navigate to Tasks page
    await sidebar.getByRole('button', { name: 'Tasks' }).click()
    await expect(page.locator('#tasks-title')).toHaveText('Tasks')
    await expect(page.locator('#planning-title')).toHaveText('Turn an objective into an approved plan')

    // 4. Navigate to Agents page
    await sidebar.getByRole('button', { name: 'Agents' }).click()
    await expect(page.locator('#agents-title')).toHaveText('Agent Monitoring')

    // 5. Navigate to Workspace page
    await sidebar.getByRole('button', { name: 'Workspace' }).click()
    await expect(page.locator('#workspace-page-title')).toHaveText('Workspace')

    // 6. Navigate to Settings page
    await sidebar.getByRole('button', { name: 'Settings' }).click()
    await expect(page.locator('h1')).toContainText('Settings')

    // 7. Navigate back to Office page
    await sidebar.getByRole('button', { name: 'Office' }).click()
    await expect(page.locator('#workspace-title')).toHaveText('Your AI Workspace')
    await expect(page.locator('.office-viewport')).toBeVisible()

    // 8. Assert no uncaught page errors
    expect(pageErrors).toHaveLength(0)
  })
})
