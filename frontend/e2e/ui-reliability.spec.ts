import { test, expect } from '@playwright/test'

test.describe('Test I, J & K: Responsive Layout, Error Boundaries & Polling Cleanup', () => {
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

    await page.route('**/api/v1/conversations*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    })

    await page.route('**/api/v1/tasks*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    })
  })

  // Test I: Responsive Viewports
  const viewports = [
    { name: 'Desktop (1440x900)', width: 1440, height: 900, isDrawer: false },
    { name: 'Laptop (1366x768)', width: 1366, height: 768, isDrawer: false },
    { name: 'Tablet (768x1024)', width: 768, height: 1024, isDrawer: true },
    { name: 'Mobile (390x844)', width: 390, height: 844, isDrawer: true },
  ]

  for (const vp of viewports) {
    test(`renders responsively at ${vp.name} without layout breaks`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height })
      await page.goto('/')

      await expect(page.locator('.app-header')).toBeVisible()

      if (vp.isDrawer) {
        // Drawer navigation test for width <= 900px
        const menuBtn = page.getByRole('button', { name: 'Open workspace menu' })
        await expect(menuBtn).toBeVisible()
        await menuBtn.click()

        // Drawer should open
        const sidebar = page.locator('#workspace-sidebar')
        await expect(sidebar).toHaveClass(/app-sidebar--open/)

        // Navigate via drawer
        await sidebar.getByRole('button', { name: 'Tasks' }).click()
        await expect(page.locator('#tasks-title')).toBeVisible()
      } else {
        // Desktop / Laptop sidebar
        const sidebar = page.locator('#workspace-sidebar')
        await expect(sidebar).toBeVisible()
        await sidebar.getByRole('button', { name: 'Tasks' }).click()
        await expect(page.locator('#tasks-title')).toBeVisible()
      }

      // Check no fatal React crash occurred
      await expect(page.locator('.main-content')).toBeVisible()
    })
  }

  // Test J: Browser Error Handling
  test('handles network failure without white screen or crashing React root', async ({ page }) => {
    const pageErrors: Error[] = []
    page.on('pageerror', (err) => pageErrors.push(err))

    // Simulate complete network failure on tasks endpoint
    await page.route('**/api/v1/tasks*', async (route) => {
      await route.abort('failed')
    })

    await page.goto('/')
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Tasks' }).click()

    // Error alert should be displayed in tasks board
    const errorAlert = page.locator('.tasks-state--error')
    await expect(errorAlert).toBeVisible()
    await expect(errorAlert).toContainText(/Failed to fetch|Unable to load/)

    // App header and navigation must remain functional
    await expect(page.locator('.app-header')).toBeVisible()
    await expect(page.locator('#workspace-sidebar')).toBeVisible()

    // No uncaught React runtime exceptions
    expect(pageErrors).toHaveLength(0)
  })

  // Test K: Polling & Component Unmount Cleanup
  test('polling requests cease cleanly when component unmounts', async ({ page }) => {
    let activityPollCount = 0

    await page.route('**/api/v1/agents/activities', async (route) => {
      activityPollCount++
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    })

    await page.goto('/')
    // Wait for at least 1 initial fetch
    await page.waitForTimeout(1000)
    const countAtMount = activityPollCount
    expect(countAtMount).toBeGreaterThanOrEqual(1)

    // Navigate away to Settings (unmounts OfficeViewport)
    await page.locator('#workspace-sidebar').getByRole('button', { name: 'Settings' }).click()
    await expect(page.locator('h1')).toContainText('Settings')

    // Record count right after unmount
    const countAfterUnmount = activityPollCount

    // Wait 3.5 seconds
    await page.waitForTimeout(3500)

    // Activity poll interval is 3000ms. Since unmounted, it should NOT have continued polling rapidly
    // Allow at most 1 in-flight completion
    expect(activityPollCount - countAfterUnmount).toBeLessThanOrEqual(1)
  })
})
