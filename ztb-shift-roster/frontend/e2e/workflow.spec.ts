import { expect, test, type Page } from '@playwright/test'

// Primary workflow on SYNTHETIC data, end to end through the real UI and backend.
// The tests share one fresh database and run in order.
test.describe.configure({ mode: 'serial' })

const next = (page: Page) => page.getByRole('button', { name: 'Next', exact: true }).click()

test('load synthetic demo data from Settings', async ({ page }) => {
  await page.goto('/settings')
  await page.getByRole('tab', { name: 'Backup & data' }).click()
  await page.getByRole('button', { name: 'Load synthetic demo data' }).click()
  await expect(page.getByText('Synthetic demo data loaded')).toBeVisible()
  await page.goto('/analysts')
  await expect(page.getByRole('cell', { name: 'SYN-012', exact: true })).toBeVisible()
})

test('create a project with a custom shift through the UI', async ({ page }) => {
  await page.goto('/projects')
  await page.getByRole('button', { name: 'New project' }).click()
  await page.getByLabel('Code').fill('E2E')
  await page.getByLabel('Name').fill('E2E synthetic project')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Project created')).toBeVisible()
  const card = page.locator('[data-slot="card"]', { hasText: 'E2E synthetic project' })
  await card.getByRole('button', { name: 'Add shift' }).click()
  await page.getByLabel('Code').fill('D')
  await page.getByLabel('Name').fill('Day')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(card.getByText('09:00–18:00')).toBeVisible()
})

test('submit and approve leave, then see it on the calendar', async ({ page }) => {
  await page.goto('/leave')
  await page.getByRole('button', { name: 'Submit leave' }).click()
  await page.getByLabel('Analyst').selectOption({ label: 'SYN-005 · Rohan Synthetic' })
  const month = await page.evaluate(() => {
    const d = new Date(); const n = new Date(d.getFullYear(), d.getMonth() + 1, 1)
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}`
  })
  await page.getByLabel('From', { exact: true }).fill(`${month}-22`)
  await page.getByLabel('To', { exact: true }).fill(`${month}-23`)
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Leave submitted')).toBeVisible()
  const row = page.getByRole('row', { name: /SYN-005/ }).filter({ hasText: `${month}-22` })
  await row.getByRole('button', { name: 'Approve' }).click()
  await expect(row.getByText('approved')).toBeVisible()
  await page.getByRole('tab', { name: 'Leave calendar' }).click()
  await expect(page.getByTestId('leave-calendar')).toBeVisible()
})

test('generate a roster with the wizard, edit it, undo, publish and export', async ({ page }) => {
  await page.goto('/generate')
  await next(page)
  await page.getByLabel('Project SYN-A').click()
  await page.getByLabel('Project SYN-B').click()
  await next(page)
  await expect(page.getByText('12 selected')).toBeVisible()
  await next(page)
  await expect(page.getByText('How leave is used')).toBeVisible()
  await next(page)
  await page.getByLabel('Solver time limit (seconds)').fill('20')
  await next(page)
  await page.getByRole('button', { name: 'Run feasibility check' }).click()
  await expect(page.getByTestId('feasibility')).toContainText('No blockers found')
  await next(page)
  await page.getByRole('button', { name: 'Generate roster' }).click()
  await expect(page.getByTestId('job-progress')).toBeVisible()
  await expect(page.getByText('Run finished')).toBeVisible({ timeout: 120_000 })
  await next(page)
  await expect(page.getByTestId('wizard-validation')).toContainText('every hard rule holds')
  await next(page)
  await next(page)
  await page.getByRole('link', { name: 'Open roster editor' }).click()

  const matrix = page.getByTestId('roster-matrix')
  await expect(matrix).toBeVisible()
  await expect(page.getByTestId('validation-summary')).toContainText('Valid')

  // Drag a shift onto an off day of the same analyst; the change is validated before saving.
  const row = matrix.locator('tbody tr').first()
  const shift = row.locator('td span[draggable="true"]').first()
  const offCell = row.locator('td', { hasText: /^WO$/ }).first()
  await shift.dragTo(offCell)
  const dialog = page.getByRole('dialog')
  await expect(dialog.or(page.getByText('Change saved', { exact: true }))).toBeVisible()
  if (await dialog.isVisible()) {
    await expect(dialog).toContainText('breaks hard rules')
    await dialog.getByLabel('Override reason').fill('E2E synthetic override test')
    await dialog.getByRole('button', { name: 'Save with override' }).click()
    await expect(page.getByText('Change saved with override')).toBeVisible()
  }
  await expect(page.getByRole('button', { name: 'Undo' })).toBeEnabled()
  await page.getByRole('button', { name: 'Undo' }).click()
  await expect(page.getByTestId('validation-summary')).toContainText('Valid', { timeout: 20_000 })
  await expect(page.getByRole('button', { name: 'Redo' })).toBeEnabled()

  // Lock an assignment through the cell editor.
  await row.locator('td span[draggable="true"]').first().click()
  await page.getByRole('button', { name: 'Lock assignment' }).click()
  await expect(page.getByText('Change saved', { exact: true }).last()).toBeVisible()
  await expect(row.getByText(/🔒/).first()).toBeVisible()

  // Other views render.
  await page.getByRole('tab', { name: 'Shift view' }).click()
  await expect(page.getByTestId('shift-view')).toBeVisible()
  await page.getByRole('tab', { name: 'Week' }).click()
  await expect(page.getByTestId('calendar-timeGridWeek').locator('.fc-event').first()).toBeVisible()

  // Export.
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export XLSX' }).click()
  expect((await download).suggestedFilename()).toMatch(/^shiftorbit-roster-\d{4}-\d{2}-v1\.xlsx$/)

  // Publish: the roster becomes read-only.
  await page.getByRole('button', { name: 'Publish' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Publish' }).click()
  await expect(page.getByText('This roster is published and read-only')).toBeVisible()
  await expect(page.getByRole('button', { name: 'New draft version' })).toBeVisible()
})

test('pending leave impact is simulated without changing the published roster', async ({ page }) => {
  await page.goto('/leave')
  const row = page.getByRole('row', { name: /SYN-004/ }).filter({ hasText: 'pending' })
  await row.getByRole('button', { name: 'Impact' }).click()
  await expect(page.getByText('approved (simulation; nothing is changed)')).toBeVisible()
  await expect(page.getByTestId('impact-roster').first()).toBeVisible()
})

test('dashboard shows coverage and workload for the generated month', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Next month' }).click()
  await expect(page.getByText('Coverage').first()).toBeVisible()
  await expect(page.getByRole('cell', { name: /SYN-001/ })).toBeVisible()
})

test('import analysts from CSV with preview and mapping', async ({ page }) => {
  await page.goto('/import-export')
  await page.getByLabel('What are you importing?').selectOption('analysts')
  await page.getByLabel(/File/).setInputFiles({
    name: 'analysts.csv', mimeType: 'text/csv',
    buffer: Buffer.from('Emp ID,Analyst Name,Projects\nE2E-1,Synthetic Import One,SYN-A\nE2E-2,Synthetic Import Two,SYN-B\n'),
  })
  await page.getByRole('button', { name: 'Preview' }).click()
  await expect(page.getByTestId('import-preview')).toContainText('first 2 of 2 rows')
  await page.getByRole('button', { name: 'Validate & import' }).click()
  await expect(page.getByText(/2 created/).first()).toBeVisible()
  await page.goto('/analysts')
  await expect(page.getByRole('cell', { name: 'E2E-2', exact: true })).toBeVisible()
})

test('mobile navigation works @mobile', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: 'Leave' }).click()
  await expect(page.getByRole('heading', { name: 'Leave' })).toBeVisible()
})
