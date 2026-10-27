import { test, expect } from '@playwright/test'

test.describe('Test G & H: Phaser Canvas Runtime & Agent Activity Sync', () => {
  test('mounts Phaser canvas, initializes viewport, resizes cleanly, syncs activities, and unmounts without duplicate canvas', async ({ page }) => {
    const pageErrors: Error[] = []
    page.on('pageerror', (err) => pageErrors.push(err))

    let currentActivities = [
      { agent_id: 'manager', status: 'idle', current_task_id: null, current_task_title: null, workflow_run_id: null, updated_at: new Date().toISOString() },
      { agent_id: 'developer', status: 'idle', current_task_id: null, current_task_title: null, workflow_run_id: null, updated_at: new Date().toISOString() },
      { agent_id: 'researcher', status: 'idle', current_task_id: null, current_task_title: null, workflow_run_id: null, updated_at: new Date().toISOString() },
    ]

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
        body: JSON.stringify(currentActivities),
      })
    })

    await page.route('**/api/v1/conversations*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    })

    await page.goto('/')

    // 1. Verify Phaser Canvas is mounted
    const canvas = page.locator('.office-viewport__stage canvas')
    await expect(canvas).toBeVisible()

    // 2. Verify Canvas dimensions
    const box = await canvas.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.width).toBeGreaterThan(100)
    expect(box!.height).toBeGreaterThan(100)

    // 3. Test Reset View button
    const resetViewBtn = page.getByRole('button', { name: 'Reset office camera view' })
    await expect(resetViewBtn).toBeVisible()
    await resetViewBtn.click()

    // 4. Test Toggle Chat button (triggers layout resize)
    const toggleChatBtn = page.getByRole('button', { name: 'Close AI agent chat panel' })
    await expect(toggleChatBtn).toBeVisible()
    await toggleChatBtn.click()

    // Chat should now be closed
    await expect(page.locator('#manager-ai-chat-panel')).not.toBeVisible()

    // Open Chat again
    const openChatBtn = page.getByRole('button', { name: 'Open AI agent chat panel' })
    await openChatBtn.click()
    await expect(page.locator('#manager-ai-chat-panel')).toBeVisible()

    // 5. Verify Agent Activity strip
    const activityStrip = page.locator('.agent-activity-strip')
    await expect(activityStrip).toBeVisible()
    await expect(activityStrip).toContainText('Manager')
    await expect(activityStrip).toContainText('Developer')
    await expect(activityStrip).toContainText('Researcher')

    // 6. Simulate Activity State Transition (Developer starts working on task #15)
    currentActivities = [
      { agent_id: 'manager', status: 'idle', current_task_id: null, current_task_title: null, workflow_run_id: null, updated_at: new Date().toISOString() },
      { agent_id: 'developer', status: 'working', current_task_id: 15, current_task_title: 'Building Redis Queue', workflow_run_id: 10, updated_at: new Date().toISOString() },
      { agent_id: 'researcher', status: 'idle', current_task_id: null, current_task_title: null, workflow_run_id: null, updated_at: new Date().toISOString() },
    ]

    // Wait for activity card to reflect 'working' status
    await expect(activityStrip.locator('.agent-activity-card--working')).toBeVisible({ timeout: 7000 })
    await expect(activityStrip).toContainText('Building Redis Queue')

    // 7. Verify Unmount and Remount without duplicate canvas
    const sidebar = page.locator('#workspace-sidebar')
    await sidebar.getByRole('button', { name: 'Settings' }).click()
    await expect(page.locator('.office-viewport')).not.toBeVisible()

    // Return to Office
    await sidebar.getByRole('button', { name: 'Office' }).click()
    await expect(page.locator('.office-viewport')).toBeVisible()

    // Ensure strictly ONE canvas element exists
    const canvases = page.locator('.office-viewport__stage canvas')
    await expect(canvases).toHaveCount(1)

    // 8. Test Office Layout Editor (TASK 36)
    const editLayoutBtn = page.getByRole('button', { name: 'Edit office layout' })
    await expect(editLayoutBtn).toBeVisible()
    await editLayoutBtn.click()

    // Verify Editor Toolbar
    const editorToolbar = page.locator('.layout-editor-bar')
    await expect(editorToolbar).toBeVisible()
    await expect(editorToolbar).toContainText('EDITING')
    await expect(page.locator('.office-viewport__status')).toContainText('Editing layout')

    // Test Default and Save buttons
    const defaultBtn = page.getByRole('button', { name: 'Reset to default office layout' })
    await expect(defaultBtn).toBeVisible()
    await defaultBtn.click()

    const saveLayoutBtn = page.getByRole('button', { name: 'Save current office layout' })
    await expect(saveLayoutBtn).toBeVisible()
    await saveLayoutBtn.click()

    // Verify exit from edit mode
    await expect(editorToolbar).not.toBeVisible()
    await expect(page.locator('.office-viewport__status')).toContainText('Office online')

    // Ensure no uncaught runtime exceptions occurred
    expect(pageErrors).toHaveLength(0)
  })
})

