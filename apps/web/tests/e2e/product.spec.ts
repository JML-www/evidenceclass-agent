import { expect, test } from '@playwright/test'

test('task centre exposes the core product workflow', async ({ page }) => {
  await page.goto('/jobs')
  await expect(page.getByRole('heading', { name: '任务中心' })).toBeVisible()
  await expect(page.getByText('高一数学 · 函数单调性')).toBeVisible()
  await page.getByRole('link', { name: '新建分析' }).click()
  await expect(page.getByRole('heading', { name: '新建分析' })).toBeVisible()
  await page.getByRole('button', { name: /开始分析/ }).click()
  await expect(page.getByText(/正在创建任务|执行进度/)).toBeVisible({ timeout: 5_000 })
})

test('evidence browser distinguishes raw, deterministic, and explanation layers', async ({ page }) => {
  await page.goto('/evidence')
  await expect(page.getByRole('heading', { name: '证据浏览器' })).toBeVisible()
  await expect(page.getByText('原始观察').first()).toBeVisible()
  await expect(page.getByText('确定性结果').first()).toBeVisible()
  await expect(page.getByText(/LLM 解释/).first()).toBeVisible()
})

test('review workspace has an accessible decision form', async ({ page }) => {
  await page.goto('/reviews')
  await expect(page.getByRole('heading', { name: '复核工作台' })).toBeVisible()
  await expect(page.getByLabel('审核理由')).toBeEditable()
  await expect(page.getByRole('button', { name: /确认并继续/ })).toBeVisible()
})

test('report Q&A persists messages, renders citations, and explains missing evidence', async ({ page }) => {
  await page.goto('/results')
  const input = page.getByLabel('向报告提问')
  await input.fill('当前报告有哪些可核查观察？')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('EV-042').first()).toBeVisible()
  await expect(page.getByText('来源：deterministic/mock')).toBeVisible()
  await page.getByRole('button', { name: /EV-042/ }).first().click()
  await expect(page.getByRole('heading', { name: '证据浏览器' })).toBeVisible()
  await page.goto('/results')
  await expect(page.getByLabel('向报告提问')).toBeVisible()

  await page.getByLabel('向报告提问').fill('没有证据时可以猜测吗？')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('未找到足够证据')).toBeVisible()
  await expect(page.getByText('来源：unavailable_fallback')).toBeVisible()
})

test('task, run, and review actions update the offline state', async ({ page }) => {
  await page.goto('/jobs')
  const failedRow = page.locator('tr').filter({ hasText: '初一英语 · 口语互动' })
  await failedRow.getByRole('button', { name: /打开 .*操作菜单/ }).click()
  await failedRow.getByRole('button', { name: '重试任务' }).click()
  await expect(failedRow.getByText('运行中')).toBeVisible()

  await page.goto('/runs/job_8f21')
  await page.getByRole('button', { name: '取消任务' }).click()
  await expect(page.getByText('已取消', { exact: true })).toBeVisible()

  await page.goto('/reviews')
  await page.getByLabel('审核理由').fill('确认该观察与原始帧一致')
  await page.getByRole('button', { name: /确认并继续/ }).click()
  await expect(page.getByText('已记录 · APPROVED')).toBeVisible()
})
