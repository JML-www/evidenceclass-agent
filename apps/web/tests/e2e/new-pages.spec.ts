import { expect, test } from '@playwright/test'

test('sidebar exposes the three new pages', async ({ page }) => {
  await page.goto('/jobs')
  await expect(
    page.getByRole('link', { name: '知识库' }),
  ).toBeVisible()
  await expect(
    page.getByRole('link', { name: '评测中心' }),
  ).toBeVisible()
  await expect(
    page.getByRole('link', { name: '设置与模型能力' }),
  ).toBeVisible()
})

test('knowledge page lists reference materials', async ({ page }) => {
  await page.goto('/knowledge')
  await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible()
  // Mock 模式下的示例数据应可见，而不是空状态。
  await expect(
    page.getByText('高一数学 · 函数单调性 教学计划.pdf'),
  ).toBeVisible()
  await expect(page.getByText('3 份参考材料')).toBeVisible()
  await expect(page.getByText('Mock 模式')).toBeVisible()
})

test('evaluation page shows datasets without fabricated metrics', async ({ page }) => {
  await page.goto('/evaluation')
  await expect(page.getByRole('heading', { name: '评测中心' })).toBeVisible()
  await expect(page.getByText('感知（perception）')).toBeVisible()
  await expect(page.getByText('检索（retrieval）')).toBeVisible()
  await expect(page.getByText('Agent（agent）')).toBeVisible()
  await expect(page.getByText('52 条')).toBeVisible()
  await expect(page.getByText('证据可追溯率')).toBeVisible()
  // 诚实标注：不编造评测指标，明确本地报告生成方式。
  await expect(
    page.getByText(/scripts\/accept-stage-11\.ps1/),
  ).toBeVisible()
})

test('settings page shows model capability boundaries', async ({ page }) => {
  await page.goto('/settings')
  await expect(
    page.getByRole('heading', { name: '设置与模型能力' }),
  ).toBeVisible()
  await expect(page.getByText('本地 Qwen3.5-0.8B')).toBeVisible()
  await expect(page.getByText('FunASR')).toBeVisible()
  await expect(page.getByText('RapidOCR')).toBeVisible()
  await expect(page.getByText('未接入', { exact: true })).toBeVisible()
  await expect(page.getByText('不做学生身份识别')).toBeVisible()
})
