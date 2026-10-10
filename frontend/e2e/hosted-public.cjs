/* Bounded hosted public-example checks. No provider calls or reviewer secrets. */
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const { chromium } = require('@playwright/test')
const base = 'https://spotter-atlas-assessment.pages.dev'
const api = 'https://spotter-atlas-assessment-api.onrender.com/api/v1'
const allowed = new Set([new URL(base).hostname, new URL(api).hostname])
const output = path.resolve(__dirname, '../../docs/deployment/evidence/2026-10-11/browser')
fs.mkdirSync(output, { recursive: true })
const result = {
  status: 'RUNNING',
  checks: [],
  errors: [],
  unexpected_requests: [],
  provider_calls: 0,
  started_at: new Date().toISOString(),
  renderer: 'Hosted Chrome with SwiftShader; no physical GPU certification',
}
let browser
async function check(name, fn) {
  const start = performance.now()
  await fn()
  result.checks.push({ name, status: 'PASS', milliseconds: Math.round(performance.now() - start) })
}
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
      const page = await context.newPage()
      page.setDefaultTimeout(60000)
      let creations = 0
      let calls = 0
      page.on('pageerror', (error) => result.errors.push(error.message))
      page.on('request', (r) => {
        if (r.url().startsWith(api)) {
          calls++
          if (r.method() === 'POST' && r.url().endsWith('/analyses/')) creations++
        }
      })
      await context.route('**/*', async (route) => {
        const url = new URL(route.request().url())
        if (!allowed.has(url.hostname) && !['data:', 'blob:'].includes(url.protocol)) {
          result.unexpected_requests.push(url.origin + url.pathname)
          return route.abort()
        }
        assert.ok(calls < 60, 'Per-viewport hosted API request ceiling')
        await route.continue()
      })
      await check(`Hosted anonymous entry, HTTPS/CSP and MapLibre ${viewport.width}`, async () => {
        const response = await page.goto(base, { waitUntil: 'domcontentloaded', timeout: 120000 })
        assert.equal(response.status(), 200)
        const headers = response.headers()
        assert.equal(headers['x-frame-options'], 'DENY')
        assert.equal(headers['x-content-type-options'], 'nosniff')
        assert.ok(headers['content-security-policy'].includes("worker-src 'self' blob:"))
        await page.getByTestId('recommendation').waitFor()
        await page.getByText('Example trip', { exact: true }).waitFor()
        assert.equal(await page.getByLabel('Private reviewer access code').count(), 0)
        await page.waitForFunction(() => {
          const node = document.querySelector('[data-testid="operational-map"]')
          return node?.dataset.renderer === 'maplibre' && node?.dataset.visualReady === 'true'
        })
        assert.equal(creations, 0)
        const body = await page.locator('body').innerText()
        assert.ok(
          !/\b(demo|assessment|reviewer)\b/i.test(
            body.replaceAll('atlas-assessment-policy-v1.0.0', ''),
          ),
        )
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
          true,
        )
        await page.screenshot({ path: path.join(output, `dispatch-${viewport.width}.png`) })
      })
      await check(
        `Hosted checkpoint selection and immutable preference ${viewport.width}`,
        async () => {
          const before = await (await page.request.get(`${api}/examples/complete/`)).json()
          assert.equal(before.recommendation.route_id, 'route-b')
          if (viewport.width === 390) {
            await page.getByRole('button', { name: '3 routes', exact: true }).click()
            await page
              .getByRole('dialog')
              .getByRole('button', { name: /Inspect Route A/ })
              .click()
          } else
            await page
              .getByRole('button', { name: /Inspect Route A/ })
              .first()
              .click()
          const after = await (await page.request.get(`${api}/analyses/${before.id}/`)).json()
          assert.deepEqual(after.recommendation, before.recommendation)
          assert.equal(after.id, before.id)
        },
      )
      await check(
        `Hosted keyboard forecast 0/48 and Unknown legend ${viewport.width}`,
        async () => {
          if (viewport.width === 390)
            await page.getByRole('link', { name: 'Forecast', exact: true }).click()
          const slider = page.getByRole('slider')
          await slider.focus()
          await slider.press('End')
          await page.getByRole('button', { name: 'Snow', exact: true }).click()
          await page.getByText(/Displayed: \+48h snow/).waitFor()
          assert.equal(await slider.inputValue(), '48')
          assert.ok(await page.getByText(/Unknown cells stay unclassified/).isVisible())
          await page.screenshot({ path: path.join(output, `forecast-${viewport.width}.png`) })
          await slider.press('Home')
          await page.getByRole('button', { name: 'Wind', exact: true }).click()
          await page.getByText(/Displayed: \+0h wind/).waitFor()
        },
      )
      await check(`Hosted protected planner retains draft ${viewport.width}`, async () => {
        if (viewport.width === 390)
          await page.getByRole('link', { name: 'Dispatch', exact: true }).click()
        await page.getByRole('button', { name: 'Plan Route', exact: true }).first().click()
        await page.getByLabel('Cargo load · pounds').fill('30000.01')
        await page.getByRole('button', { name: 'Analyze Route', exact: true }).click()
        await page
          .getByRole('dialog')
          .getByText(/operation is restricted/)
          .waitFor()
        assert.equal(await page.getByLabel('Cargo load · pounds').inputValue(), '30000.01')
        await page.screenshot({ path: path.join(output, `planning-${viewport.width}.png`) })
        await page.keyboard.press('Escape')
      })
      if (process.env.ATLAS_REVIEWER_CODE) {
        await check(
          `Explicit private planning authorization, live still disabled ${viewport.width}`,
          async () => {
            await page.getByRole('button', { name: 'Plan Route', exact: true }).first().click()
            await page.getByRole('button', { name: 'Analyze Route', exact: true }).click()
            await page
              .getByRole('dialog')
              .getByText(/operation is restricted/)
              .waitFor()
            await page.getByText('Private planning access', { exact: true }).click()
            await page
              .getByLabel('Planning access', { exact: true })
              .fill(process.env.ATLAS_REVIEWER_CODE)
            await page.getByRole('button', { name: 'Set planning access', exact: true }).click()
            assert.equal(await page.getByLabel('Planning access', { exact: true }).inputValue(), '')
            const responsePromise = page.waitForResponse(
              (r) => r.url() === `${api}/analyses/` && r.request().method() === 'POST',
            )
            await page.getByRole('button', { name: 'Analyze Route', exact: true }).click()
            const response = await responsePromise
            assert.equal(response.status(), 503)
            assert.equal((await response.json()).error.code, 'LIVE_MODE_UNAVAILABLE')
            await page.keyboard.press('Escape')
          },
        )
      }
      await check(
        `Hosted reload without credentials or new snapshot ${viewport.width}`,
        async () => {
          const count = creations
          await page.reload()
          await page.getByTestId('recommendation').waitFor()
          assert.equal(creations, count)
          assert.deepEqual((await context.storageState()).origins, [])
        },
      )
      await context.close()
    }
    assert.deepEqual(result.errors, [])
    assert.deepEqual(result.unexpected_requests, [])
    result.status = 'PASS'
  } catch (error) {
    result.status = 'FAIL'
    result.failure = error.message
    process.exitCode = 1
  } finally {
    if (browser) await browser.close()
    result.completed_at = new Date().toISOString()
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(result, null, 2))
    console.log(JSON.stringify(result, null, 2))
  }
})()
