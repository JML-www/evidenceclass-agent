import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  // Keep the base URL aligned with the Vite dev server started below.  The
  // previous 4173 value pointed at Vite's preview default while the test
  // runner starts `vite` on 5173, so every `page.goto` failed before a test
  // could exercise the product.
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1', port: 5173, reuseExistingServer: true },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]
})
