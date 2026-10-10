/* Stored real local analysis only. No new provider calls, raw export or geometry screenshots. */
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const { chromium } = require('@playwright/test')
const root = path.resolve(__dirname, '../..')
const base = process.env.ATLAS_FRONTEND_URL || 'http://127.0.0.1:4174'
assert.equal(new URL(base).hostname, '127.0.0.1')
const id = fs.readFileSync(path.join(root, 'backend/.local/last-live-id.txt'), 'utf8').trim()
const evidenceRoot = path.join(root, 'docs/implementation/evidence')
const outputDirectory = path.resolve(
  evidenceRoot,
  process.env.ATLAS_BROWSER_EVIDENCE_SUBDIR || 'assessment-json',
)
assert.ok(!path.relative(evidenceRoot, outputDirectory).startsWith('..'))
fs.mkdirSync(outputDirectory, { recursive: true })
const output = path.join(outputDirectory, 'live-browser.json')
const results = {
  status: 'RUNNING',
  checks: [],
  errors: [],
  provider_requests: 0,
  geometry_screenshots: false,
  renderer: 'Chrome headless SwiftShader; not physical GPU',
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
      const context = await browser.newContext({ viewport, reducedMotion: 'reduce' })
      await context.route('**/*', async (route) => {
        if (/^(http:\/\/127\.0\.0\.1:\d+\/|data:|blob:)/.test(route.request().url()))
          await route.continue()
        else {
          results.provider_requests++
          await route.abort()
        }
      })
      const page = await context.newPage()
      page.on('pageerror', (error) => results.errors.push(error.message))
      const before = await page.request.get(`${base}/api/v1/analyses/${id}/`)
      assert.equal(before.status(), 200)
      const saved = await before.json()
      assert.equal(saved.mode, 'live')
      const start = performance.now()
      await page.goto(`${base}/?analysis=${id}`, { waitUntil: 'networkidle' })
      await page.getByTestId('recommendation').waitFor()
      assert.ok(
        await page.getByText('LIVE FORECAST · ASSESSMENT', { exact: true }).first().isVisible(),
      )
      assert.ok(await page.getByText(/snowfall uses a disclosed fixed 7:1/).isVisible())
      await page.waitForFunction(
        () =>
          document.querySelector('[data-testid="operational-map"]')?.dataset.visualReady === 'true',
      )
      const mapRenderer = await page.getByTestId('operational-map').getAttribute('data-renderer')
      assert.ok(
        await page.locator('.map-canvas').evaluate((el) => el.getBoundingClientRect().height > 250),
        'Live map must have visible canvas height',
      )
      assert.equal(mapRenderer, 'maplibre')
      assert.equal(await page.locator('[data-testid^="route-"]').count(), 3)
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
        true,
      )
      results.checks.push({
        name: `Stored live run renders ${viewport.width}x${viewport.height}`,
        status: 'PASS',
        milliseconds: Math.round(performance.now() - start),
        mapRenderer,
      })
      if (viewport.width === 1440) {
        const route = page.getByTestId('route-B')
        await route.focus()
        await page.keyboard.press('Enter')
        assert.equal(await route.getAttribute('aria-pressed'), 'true')
        await page.getByLabel('Requested forecast hour offset').fill('48')
        await page.getByText(/forecast samples ·/).waitFor()
        await page.getByRole('button', { name: 'Snow', exact: true }).click()
        await page.getByText(/Displayed: \+48h snow/).waitFor()
        const after = await page.request.get(`${base}/api/v1/analyses/${id}/`)
        assert.deepEqual((await after.json()).recommendation, saved.recommendation)
        results.checks.push({
          name: 'Keyboard route selection +48h snowfall keeps backend recommendation',
          status: 'PASS',
        })
      } else {
        await page.getByRole('button', { name: '3 routes', exact: true }).click()
        const dialog = page.getByRole('dialog')
        await dialog.waitFor()
        assert.equal(await dialog.locator('[data-testid^="route-"]').count(), 3)
        await page.keyboard.press('Escape')
        results.checks.push({
          name: 'Mobile same-analysis route dialog and Escape interaction',
          status: 'PASS',
        })
      }
      await context.close()
    }
    assert.equal(results.provider_requests, 0)
    assert.deepEqual(results.errors, [])
    results.status = 'PASS'
  } catch (error) {
    results.status = 'FAIL'
    results.failure = error.message
    process.exitCode = 1
  } finally {
    if (browser) await browser.close()
    results.completed_at = new Date().toISOString()
    fs.writeFileSync(output, JSON.stringify(results, null, 2))
    console.log(JSON.stringify(results, null, 2))
  }
})()
