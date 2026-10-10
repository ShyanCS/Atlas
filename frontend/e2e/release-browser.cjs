/* Authored reviewer code; credential-free local sample release, never providers. */
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const { chromium } = require('@playwright/test')
const base = process.env.ATLAS_RELEASE_FRONTEND_URL || 'http://127.0.0.1:4175'
assert.equal(new URL(base).hostname, '127.0.0.1')
const code = 'authored-browser-reviewer-code-for-tests'
const csp = fs
  .readFileSync(path.resolve(__dirname, '../public/_headers'), 'utf8')
  .split('\n')
  .find((line) => line.trim().startsWith('Content-Security-Policy:'))
  .trim()
  .slice('Content-Security-Policy:'.length)
  .trim()
const output = path.resolve(__dirname, '../../docs/implementation/evidence/deployment-preparation')
fs.mkdirSync(output, { recursive: true })
const results = {
  status: 'RUNNING',
  checks: [],
  errors: [],
  external_requests: 0,
  started_at: new Date().toISOString(),
}
let browser
;(async () => {
  try {
    browser = await chromium.launch({
      channel: 'chrome',
      headless: true,
      args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
    })
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 390, height: 844 },
    ]) {
      const context = await browser.newContext({ viewport })
      const page = await context.newPage()
      let submissions = 0
      page.on('pageerror', (error) => results.errors.push(error.message))
      page.on('request', (request) => {
        if (request.method() === 'POST' && request.url().includes('/analyses/')) submissions++
      })
      await context.route('**/*', async (route) => {
        if (!/^(http:\/\/127\.0\.0\.1:\d+\/|data:|blob:)/.test(route.request().url())) {
          results.external_requests++
          return route.abort()
        }
        if (route.request().resourceType() === 'document') {
          const response = await route.fetch()
          return route.fulfill({
            response,
            headers: { ...response.headers(), 'content-security-policy': csp },
          })
        }
        await route.continue()
      })
      await context.route('**/api/v1/health/', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 6500))
        await route.continue()
      })
      await page.goto(base, { waitUntil: 'domcontentloaded' })
      await page
        .getByText('The free backend or database may be waking.', { exact: false })
        .waitFor()
      assert.equal(submissions, 0)
      const input = page.getByLabel('Private reviewer access code')
      await input.waitFor()
      assert.ok(await input.isVisible())
      results.checks.push({
        name: `Cold-start message and locked access ${viewport.width}x${viewport.height}`,
        status: 'PASS',
      })
      await input.fill('incorrect-authored-code-for-tests')
      await page.getByRole('button', { name: 'Open Dispatch Canvas' }).click()
      await page.getByRole('alert').waitFor()
      assert.equal(submissions, 0)
      await input.fill(code)
      await page.getByRole('button', { name: 'Open Dispatch Canvas' }).click()
      await page.getByRole('button', { name: 'Explore Demo', exact: true }).waitFor()
      await page.getByRole('button', { name: 'Explore Demo', exact: true }).click()
      await page.getByTestId('recommendation').waitFor()
      assert.equal(submissions, 1)
      await page.waitForFunction(
        () =>
          document.querySelector('[data-testid="operational-map"]')?.dataset.renderer ===
            'maplibre' &&
          document.querySelector('[data-testid="operational-map"]')?.dataset.visualReady === 'true',
      )
      assert.equal(
        await page.getByTestId('operational-map').getAttribute('data-renderer'),
        'maplibre',
      )
      assert.ok(
        await page.locator('.map-canvas').evaluate((el) => el.getBoundingClientRect().height > 250),
        'Map container must have visible height after lazy CSS loading',
      )
      const storage = await context.storageState()
      assert.ok(!JSON.stringify(storage).includes(code))
      assert.equal(await page.evaluate(() => sessionStorage.length), 0)
      await page.screenshot({ path: path.join(output, `protected-sample-${viewport.width}.png`) })
      results.checks.push({
        name: `Reviewer unlock, genuine sample API, no provider credentials, tab-only code ${viewport.width}x${viewport.height}`,
        status: 'PASS',
      })
      await page.reload({ waitUntil: 'domcontentloaded' })
      await page.getByLabel('Private reviewer access code').waitFor()
      assert.equal(submissions, 1)
      results.checks.push({
        name: `Reload clears access without resubmission ${viewport.width}`,
        status: 'PASS',
      })
      await context.close()
    }
    assert.equal(results.external_requests, 0)
    assert.deepEqual(results.errors, [])
    results.status = 'PASS'
  } catch (error) {
    results.status = 'FAIL'
    results.failure = error.message
    process.exitCode = 1
  } finally {
    if (browser) await browser.close()
    results.completed_at = new Date().toISOString()
    fs.writeFileSync(path.join(output, 'release-browser.json'), JSON.stringify(results, null, 2))
    console.log(JSON.stringify(results, null, 2))
  }
})()
