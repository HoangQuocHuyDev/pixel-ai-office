import { test, expect } from '@playwright/test'

test.describe('Test E: Workflow Failure Recovery & Retry UI', () => {
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

    await page.route('**/api/v1/tasks*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    })

    await page.route('**/api/v1/plans?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 401, title: 'Failure Recovery Plan', objective: 'Verify safe workflow retry', status: 'approved', created_at: new Date().toISOString(), task_count: 2 },
        ]),
      })
    })

    await page.route('**/api/v1/plans/401', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 401,
          title: 'Failure Recovery Plan',
          objective: 'Verify safe workflow retry',
          status: 'approved',
          created_at: new Date().toISOString(),
          tasks: [
            { id: 21, plan_id: 401, sequence_order: 1, title: 'Initial Analysis', description: 'Analyze requirements', priority: 'high', assigned_agent_id: 'researcher', status: 'done' },
            { id: 22, plan_id: 401, sequence_order: 2, title: 'Implement Module', description: 'Code solution', priority: 'high', assigned_agent_id: 'developer', status: 'todo' },
          ],
        }),
      })
    })
  })

  test('displays failed workflow details, prompts confirmation, triggers retry, and shows new run lineage', async ({ page }) => {
    let retryCalled = false
    let currentRun = {
      id: 501,
      plan_id: 401,
      status: 'failed',
      total_tasks: 2,
      completed_tasks: 1,
      current_task_id: null,
      current_task_title: null,
      failed_task_id: 22,
      failed_task_title: 'Implement Module',
      can_retry: true,
      retry_block_reason: null,
      retried_from_run_id: null,
      error_code: 'TASK_TIMEOUT',
      error_message: 'Worker timed out executing task 22.',
      created_at: new Date().toISOString(),
    }

    // Mock workflows list for plan 401
    await page.route('**/api/v1/plans/401/workflows*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([currentRun]),
      })
    })

    // Mock retry endpoint
    await page.route('**/api/v1/workflows/501/retry', async (route) => {
      retryCalled = true
      currentRun = {
        id: 502,
        plan_id: 401,
        status: 'running',
        total_tasks: 2,
        completed_tasks: 1,
        current_task_id: 22,
        current_task_title: 'Implement Module',
        failed_task_id: null,
        failed_task_title: null,
        can_retry: false,
        retry_block_reason: null,
        retried_from_run_id: 501,
        error_code: null,
        error_message: null,
        created_at: new Date().toISOString(),
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(currentRun),
      })
    })

    // Auto-accept confirmation dialog
    page.on('dialog', (dialog) => dialog.accept())

    await page.goto('/')
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Tasks' }).click()
    await page.locator('.approved-plans').getByRole('button', { name: /Failure Recovery Plan/ }).click()

    const planModal = page.locator('.plan-details')
    await expect(planModal).toBeVisible()

    // 1. Verify Failed State & Failed Step
    await expect(planModal.locator('.execution-status--failed')).toBeVisible()
    await expect(planModal.locator('.workflow-failed-task')).toContainText('Implement Module')
    await expect(planModal.locator('.execution-error')).toContainText('Worker timed out')

    // 2. Verify Retry Button
    const retryBtn = planModal.getByRole('button', { name: 'Retry Workflow' })
    await expect(retryBtn).toBeVisible()
    await expect(retryBtn).toBeEnabled()

    // 3. Click Retry Workflow
    await retryBtn.click()

    // 4. Verify New Run created with Retried from Run #501 tag
    await expect(planModal.locator('.workflow-lineage-tag')).toBeVisible()
    await expect(planModal.locator('.workflow-lineage-tag')).toHaveText('Retried from Run #501')

    // 5. Verify status changed to running
    await expect(planModal.locator('.execution-status--running')).toBeVisible()

    expect(retryCalled).toBe(true)
  })

  test('displays retry blocked reason when retry is ineligible', async ({ page }) => {
    await page.route('**/api/v1/plans/401/workflows*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 503,
            plan_id: 401,
            status: 'failed',
            total_tasks: 2,
            completed_tasks: 1,
            can_retry: false,
            retry_block_reason: 'Plan already has an active running workflow.',
            retried_from_run_id: null,
            created_at: new Date().toISOString(),
          },
        ]),
      })
    })

    await page.goto('/')
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Tasks' }).click()
    await page.locator('.approved-plans').getByRole('button', { name: /Failure Recovery Plan/ }).click()

    const planModal = page.locator('.plan-details')
    await expect(planModal).toBeVisible()

    // Retry button should not be present
    await expect(planModal.getByRole('button', { name: 'Retry Workflow' })).not.toBeVisible()

    // Blocked reason should be displayed
    const blockedMsg = planModal.locator('.workflow-retry-blocked')
    await expect(blockedMsg).toBeVisible()
    await expect(blockedMsg).toContainText('Plan already has an active running workflow.')
  })
})

