import { test, expect } from '@playwright/test'

test.describe('Test D: Workflow Timeline & Execution History', () => {
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

    // Setup an approved plan 301
    await page.route('**/api/v1/plans?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 301, title: 'Workflow Timeline Test Plan', objective: 'Verify complete timeline visualization', status: 'approved', created_at: new Date().toISOString(), task_count: 2 },
        ]),
      })
    })

    await page.route('**/api/v1/plans/301', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 301,
          title: 'Workflow Timeline Test Plan',
          objective: 'Verify complete timeline visualization',
          status: 'approved',
          created_at: new Date().toISOString(),
          tasks: [
            { id: 11, plan_id: 301, sequence_order: 1, title: 'Gather Research', description: 'Deep market analysis', priority: 'high', assigned_agent_id: 'researcher', status: 'done' },
            { id: 12, plan_id: 301, sequence_order: 2, title: 'Build Architecture', description: 'System design doc', priority: 'high', assigned_agent_id: 'developer', status: 'done' },
          ],
        }),
      })
    })

    // WorkflowRun for plan 301
    await page.route('**/api/v1/plans/301/workflows*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 401,
            plan_id: 301,
            status: 'completed',
            total_tasks: 2,
            completed_tasks: 2,
            can_retry: false,
            created_at: new Date().toISOString(),
          },
        ]),
      })
    })
  })

  test('renders full execution timeline with steps, handoffs, attempts, and final report', async ({ page }) => {
    // Mock the Timeline API
    await page.route('**/api/v1/workflows/401/timeline', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          workflow_id: 401,
          status: 'completed',
          plan: {
            id: 301,
            title: 'Workflow Timeline Test Plan',
            objective: 'Verify complete timeline visualization',
            status: 'approved',
            created_at: new Date().toISOString(),
            approval_timestamp_available: true,
          },
          started_at: new Date(Date.now() - 60000).toISOString(),
          completed_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          progress: {
            total_tasks: 2,
            completed_tasks: 2,
            running_tasks: 0,
            pending_tasks: 0,
            failed_tasks: 0,
            cancelled_tasks: 0,
            progress_percentage: 100.0,
          },
          steps: [
            {
              step_number: 1,
              task_id: 11,
              task_title: 'Gather Research',
              task_description: 'Deep market analysis',
              agent_id: 'researcher',
              agent_name: 'Researcher AI',
              status: 'completed',
              started_at: new Date(Date.now() - 50000).toISOString(),
              completed_at: new Date(Date.now() - 30000).toISOString(),
              duration_seconds: 20.0,
              attempts: [
                {
                  id: 1,
                  attempt_number: 1,
                  status: 'completed',
                  started_at: new Date(Date.now() - 50000).toISOString(),
                  completed_at: new Date(Date.now() - 30000).toISOString(),
                  duration_seconds: 20.0,
                  result_preview: 'Comprehensive market findings completed successfully.',
                  result_truncated: false,
                  error_code: null,
                  error_message: null,
                  artifacts: [{ id: 501, title: 'Gather Research — Result', artifact_type: 'research', agent_id: 'researcher', task_execution_id: 1, workflow_run_id: null, created_at: new Date().toISOString() }],
                },
              ],
            },
            {
              step_number: 2,
              task_id: 12,
              task_title: 'Build Architecture',
              task_description: 'System design doc',
              agent_id: 'developer',
              agent_name: 'Developer AI',
              status: 'completed',
              started_at: new Date(Date.now() - 28000).toISOString(),
              completed_at: new Date(Date.now() - 10000).toISOString(),
              duration_seconds: 18.0,
              attempts: [
                {
                  id: 2,
                  attempt_number: 1,
                  status: 'completed',
                  started_at: new Date(Date.now() - 28000).toISOString(),
                  completed_at: new Date(Date.now() - 10000).toISOString(),
                  duration_seconds: 18.0,
                  result_preview: 'Architecture spec written and verified.',
                  result_truncated: false,
                  error_code: null,
                  error_message: null,
                  artifacts: [{ id: 502, title: 'Build Architecture — Result', artifact_type: 'document', agent_id: 'developer', task_execution_id: 2, workflow_run_id: null, created_at: new Date().toISOString() }],
                },
              ],
            },
          ],
          handoffs: [
            {
              id: 1,
              workflow_run_id: 401,
              source_task_execution_id: 1,
              source_task_id: 11,
              source_task_title: 'Gather Research',
              source_agent_id: 'researcher',
              source_agent_name: 'Researcher AI',
              target_task_id: 12,
              target_task_title: 'Build Architecture',
              target_agent_id: 'developer',
              target_agent_name: 'Developer AI',
              summary: 'Market analysis deliverables handed over for system architecture design.',
              key_findings: ['High throughput requirements identified', 'Modular backend requested'],
              deliverables: ['Research synthesis v1'],
              next_steps: 'Proceed with architecture draft',
              artifacts: [{ id: 501, title: 'Gather Research — Result', artifact_type: 'research', agent_id: 'researcher', task_execution_id: 1, workflow_run_id: null, created_at: new Date().toISOString() }],
              created_at: new Date().toISOString(),
            },
          ],
          finalization: {
            status: 'completed',
            started_at: new Date(Date.now() - 9000).toISOString(),
            completed_at: new Date(Date.now() - 2000).toISOString(),
            report_preview: 'Manager Final Report: All tasks completed on schedule with zero errors.',
            report_truncated: false,
            error_code: null,
            error_message: null,
            artifacts: [{ id: 503, title: 'Workflow Timeline Test Plan — Final Report', artifact_type: 'report', agent_id: 'manager', task_execution_id: null, workflow_run_id: 401, created_at: new Date().toISOString() }],
          },
          error_code: null,
          error_message: null,
          execution_scope_note: 'Completed successfully',
        }),
      })
    })

    await page.goto('/')
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Tasks' }).click()

    // Open Approved Plan modal
    await page.locator('.approved-plans').getByRole('button', { name: /Workflow Timeline Test Plan/ }).click()
    const planModal = page.locator('.plan-details')
    await expect(planModal).toBeVisible()

    // Click View Execution Timeline
    const viewTimelineBtn = planModal.getByRole('button', { name: 'View Execution Timeline' })
    await expect(viewTimelineBtn).toBeVisible()
    await viewTimelineBtn.click()

    // Verify Timeline dialog appears
    const timelineDialog = page.locator('.workflow-timeline')
    await expect(timelineDialog).toBeVisible()

    // 1. Verify Progress
    await expect(timelineDialog).toContainText('100%')
    await expect(timelineDialog).toContainText('2/2 tasks')

    // 2. Verify Steps
    await expect(timelineDialog).toContainText('Gather Research')
    await expect(timelineDialog).toContainText('Build Architecture')
    await expect(timelineDialog.locator('.timeline-step')).toHaveCount(2)

    // 3. Verify Handoff Card
    const handoffCard = timelineDialog.locator('.timeline-handoff')
    await expect(handoffCard).toBeVisible()
    await expect(handoffCard).toContainText('Researcher AI')
    await expect(handoffCard).toContainText('Developer AI')
    await expect(handoffCard).toContainText('High throughput requirements identified')

    // 4. Verify Final Report
    const finalReport = timelineDialog.locator('.timeline-final')
    await expect(finalReport).toBeVisible()
    await expect(finalReport).toContainText('Manager Final Report: All tasks completed on schedule with zero errors.')

    // Close timeline
    await timelineDialog.getByRole('button', { name: 'Close workflow timeline' }).click()
    await expect(timelineDialog).not.toBeVisible()
  })

  test('displays friendly error message when timeline fails to load', async ({ page }) => {
    await page.route('**/api/v1/workflows/401/timeline', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { message: 'Database connection lost during timeline query.' },
        }),
      })
    })

    await page.goto('/')
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Tasks' }).click()
    await page.locator('.approved-plans').getByRole('button', { name: /Workflow Timeline Test Plan/ }).click()
    await page.locator('.plan-details').getByRole('button', { name: 'View Execution Timeline' }).click()

    const timelineDialog = page.locator('.workflow-timeline')
    await expect(timelineDialog).toBeVisible()
    const errorBox = timelineDialog.locator('.workflow-timeline__state--error')
    await expect(errorBox).toBeVisible()
    await expect(errorBox).toContainText('Unable to load workflow timeline')
  })
})
