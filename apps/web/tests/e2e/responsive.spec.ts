import { expect, test } from '@playwright/test'

test('core pages stay usable at desktop, tablet, and narrow widths', async ({ page }, testInfo) => {
  const viewports = [
    { width: 1440, height: 900 },
    { width: 1024, height: 900 },
    { width: 390, height: 844 },
  ]
  const routes = ['/jobs', '/new', '/evidence', '/reviews', '/results']

  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    for (const route of routes) {
      await page.goto(route)
      await expect(page.locator('body')).toBeVisible()
      const dimensions = await page.evaluate(() => ({
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
      }))
      expect(
        dimensions.scrollWidth,
        `${route} overflows at ${viewport.width}px`,
      ).toBeLessThanOrEqual(dimensions.innerWidth + 1)
    }

    await page.goto('/jobs')
    await page.screenshot({
      path: testInfo.outputPath(`jobs-${viewport.width}.png`),
      fullPage: true,
    })
  }
})
