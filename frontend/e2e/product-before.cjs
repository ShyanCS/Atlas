/* Capture the existing local build before cleanup; never contact hosted providers. */
const { chromium } = require('@playwright/test')
const fs = require('node:fs')
const path = require('node:path')
const out = path.resolve(
  __dirname,
  '../../docs/implementation/evidence/product-access-cleanup/before',
)
fs.mkdirSync(out, { recursive: true })
;(async () => {
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  })
  try {
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 390, height: 844 },
    ]) {
      const context = await browser.newContext({ viewport, reducedMotion: 'reduce' })
      await context.route('**/*', (route) =>
        /^(http:\/\/127\.0\.0\.1:\d+\/|data:|blob:)/.test(route.request().url())
          ? route.continue()
          : route.abort(),
      )
      const page = await context.newPage()
      page.on('pageerror', (error) => console.error(error.message))
      page.on('requestfailed', (request) =>
        console.error('Local request failed:', request.url(), request.failure()?.errorText),
      )
      await page.goto('http://127.0.0.1:4177')
      await page.getByLabel('Private reviewer access code').waitFor()
      await page.screenshot({ path: path.join(out, `access-${viewport.width}.png`) })
      await page
        .getByLabel('Private reviewer access code')
        .fill('authored-browser-reviewer-code-for-tests')
      await page.getByRole('button', { name: 'Open Dispatch Canvas' }).click()
      await page.getByRole('button', { name: 'Explore Demo', exact: true }).click()
      await page.getByTestId('recommendation').waitFor()
      await page.waitForFunction(
        () =>
          document.querySelector('[data-testid="operational-map"]')?.dataset.visualReady === 'true',
      )
      await page.getByText(/demo cells ·/).waitFor()
      await page.screenshot({ path: path.join(out, `dispatch-${viewport.width}.png`) })
      await context.close()
    }
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error.message)
  process.exitCode = 1
})
