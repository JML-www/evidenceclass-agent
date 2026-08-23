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
  await expect(page.getByText('原始观察')).toBeVisible()
  await expect(page.getByText('确定性结果')).toBeVisible()
  await expect(page.getByText(/LLM 解释/)).toBeVisible()
})

test('review workspace has an accessible decision form', async ({ page }) => {
  await page.goto('/reviews')
  await expect(page.getByRole('heading', { name: '复核工作台' })).toBeVisible()
  await expect(page.getByLabel('审核理由')).toBeEditable()
  await expect(page.getByRole('button', { name: /确认并继续/ })).toBeVisible()
})
