import { test, expect } from '@playwright/test'

test.describe('Test B & C: Manager Planning UI & Workflow Controls', () => {
  test.beforeEach(async ({ page }) => {
    // Standard mock setup for agents & activities
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
  })

  test('generates plan, displays tasks with agent assignments, approves plan, and starts workflow', async ({ page }) => {
    let proposalGenerated = false
    let planApproved = false
    let workflowStarted = false

    // Route for generating plan
    await page.route('**/api/v1/planning/generate', async (route) => {
      proposalGenerated = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          title: 'Automated Pipeline Plan',
          objective: 'Build an automated end to end data ingestion pipeline',
          tasks: [
            {
              title: 'Design Ingestion Schema',
              description: 'Research source formats and specify JSON schema',
              priority: 'high',
              assigned_agent_id: 'researcher',
              sequence_order: 1,
            },
            {
              title: 'Implement Ingestion Worker',
              description: 'Write Python ingestion processor with retry logic',
              priority: 'high',
              assigned_agent_id: 'developer',
              sequence_order: 2,
            },
          ],
        }),
      })
    })

    // Route for approving plan
    await page.route('**/api/v1/planning/approve', async (route) => {
      planApproved = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 101,
          title: 'Automated Pipeline Plan',
          objective: 'Build an automated end to end data ingestion pipeline',
          status: 'approved',
          created_at: new Date().toISOString(),
          tasks: [
            { id: 1, plan_id: 101, sequence_order: 1, title: 'Design Ingestion Schema', description: 'Research source formats', priority: 'high', assigned_agent_id: 'researcher', status: 'todo' },
            { id: 2, plan_id: 101, sequence_order: 2, title: 'Implement Ingestion Worker', description: 'Write Python ingestion processor', priority: 'high', assigned_agent_id: 'developer', status: 'todo' },
          ],
        }),
      })
    })

    // Route for fetching approved plans
    await page.route('**/api/v1/plans?*', async (route) => {
      if (planApproved) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 101, title: 'Automated Pipeline Plan', objective: 'Build an automated end to end data ingestion pipeline', status: 'approved', created_at: new Date().toISOString(), task_count: 2 },
          ]),
        })
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
      }
    })

    await page.route('**/api/v1/plans/101', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 101,
          title: 'Automated Pipeline Plan',
          objective: 'Build an automated end to end data ingestion pipeline',
          status: 'approved',
          created_at: new Date().toISOString(),
          tasks: [
            { id: 1, plan_id: 101, sequence_order: 1, title: 'Design Ingestion Schema', description: 'Research source formats', priority: 'high', assigned_agent_id: 'researcher', status: 'todo' },
            { id: 2, plan_id: 101, sequence_order: 2, title: 'Implement Ingestion Worker', description: 'Write Python ingestion processor', priority: 'high', assigned_agent_id: 'developer', status: 'todo' },
          ],
        }),
      })
    })

    // Route for workflows of plan 101
    await page.route('**/api/v1/plans/101/workflows*', async (route) => {
      if (route.request().method() === 'POST') {
        workflowStarted = true
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 201,
            plan_id: 101,
            status: 'running',
            total_tasks: 2,
            completed_tasks: 0,
            current_task_id: 1,
            current_task_title: 'Design Ingestion Schema',
            current_agent_id: 'researcher',
            can_retry: false,
            created_at: new Date().toISOString(),
          }),
        })
      } else {
        if (workflowStarted) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
              {
                id: 201,
                plan_id: 101,
                status: 'running',
                total_tasks: 2,
                completed_tasks: 0,
                current_task_id: 1,
                current_task_title: 'Design Ingestion Schema',
                current_agent_id: 'researcher',
                can_retry: false,
                created_at: new Date().toISOString(),
              },
            ]),
          })
        } else {
          await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
        }
      }
    })

    await page.goto('/')
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Tasks' }).click()

    // 1. Enter Objective
    const objectiveInput = page.locator('#planning-objective')
    await expect(objectiveInput).toBeVisible()
    await objectiveInput.fill('Build an automated end to end data ingestion pipeline')

    // 2. Click Generate Plan
    const generateBtn = page.getByRole('button', { name: 'Generate Plan' })
    await expect(generateBtn).toBeEnabled()
    await generateBtn.click()

    // 3. Verify Proposal Rendered
    const proposalSection = page.locator('.plan-proposal')
    await expect(proposalSection).toBeVisible()
    await expect(proposalSection.getByRole('heading', { level: 3 })).toHaveText('Automated Pipeline Plan')
    await expect(proposalSection).toContainText('Researcher AI')
    await expect(proposalSection).toContainText('Developer AI')

    // 4. Click Approve Plan
    const approveBtn = proposalSection.getByRole('button', { name: 'Approve Plan' })
    await approveBtn.click()

    // 5. Modal should be automatically visible upon approval with Workflow Controls
    const planModal = page.locator('.plan-details')
    await expect(planModal).toBeVisible()
    const startWorkflowBtn = planModal.getByRole('button', { name: 'Start Workflow' })
    await expect(startWorkflowBtn).toBeVisible()

    // 7. Start Workflow
    await startWorkflowBtn.click()

    // 8. Verify Workflow Status is running
    await expect(planModal.locator('.workflow-status')).toBeVisible()
    await expect(planModal.locator('.execution-status--running')).toBeVisible()
    await expect(planModal).toContainText('0/2 tasks')
    await expect(planModal.getByRole('button', { name: 'Cancel Workflow' })).toBeVisible()

    expect(proposalGenerated).toBe(true)
    expect(planApproved).toBe(true)
    expect(workflowStarted).toBe(true)
  })

  test('handles planning API errors gracefully without crashing UI', async ({ page }) => {
    // Mock 500 error on planning generate
    await page.route('**/api/v1/planning/generate', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'AI_SERVICE_UNAVAILABLE', message: 'Planning service temporarily unavailable.' },
        }),
      })
    })

    await page.goto('/')
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Tasks' }).click()

    const objectiveInput = page.locator('#planning-objective')
    await objectiveInput.fill('Test error handling when planning fails')

    const generateBtn = page.getByRole('button', { name: 'Generate Plan' })
    await generateBtn.click()

    // Error alert should be displayed
    const errorAlert = page.locator('.planning-error')
    await expect(errorAlert).toBeVisible()
    await expect(errorAlert).toContainText('Planning service temporarily unavailable.')

    // Objective text should remain intact
    await expect(objectiveInput).toHaveValue('Test error handling when planning fails')
    await expect(generateBtn).toBeEnabled()
  })
})
