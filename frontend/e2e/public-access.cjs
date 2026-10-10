/* Local public-example release checks; no provider data or credentials. */
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const { chromium } = require('@playwright/test')
const base = process.env.ATLAS_RELEASE_FRONTEND_URL || 'http://127.0.0.1:4177'
assert.equal(new URL(base).hostname, '127.0.0.1')
const csp = fs
  .readFileSync(path.resolve(__dirname, '../public/_headers'), 'utf8')
  .split('\n')
  .find((line) => line.trim().startsWith('Content-Security-Policy:'))
  .trim()
  .slice('Content-Security-Policy:'.length)
  .trim()
const output = path.resolve(
  __dirname,
  '../../docs/implementation/evidence/product-access-cleanup/after',
)
fs.mkdirSync(output, { recursive: true })
const results = {
  status: 'RUNNING',
  checks: [],
  errors: [],
  external_requests: [],
  provider_calls: 0,
  started_at: new Date().toISOString(),
  renderer: 'Headless Chrome SwiftShader; not a physical GPU or hosted test',
}
let browser
async function check(name, fn) {
  await fn()
  results.checks.push({ name, status: 'PASS' })
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
      let posts = 0
      page.on('pageerror', (error) => results.errors.push(error.message))
      page.on('request', (request) => {
        if (request.method() === 'POST') posts++
      })
      await context.route('**/*', async (route) => {
        if (!/^(http:\/\/127\.0\.0\.1:\d+\/|data:|blob:)/.test(route.request().url())) {
          results.external_requests.push(route.request().url())
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
      await context.route('**/api/v1/scenarios/', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 6500))
        await route.continue()
      })
      await check(`Direct shell and controlled cold-start feedback ${viewport.width}`, async () => {
        await page.goto(base, { waitUntil: 'domcontentloaded' })
        await page.getByRole('heading', { name: 'Chicago → Atlanta', exact: true }).waitFor()
        assert.equal(await page.getByLabel('Private reviewer access code').count(), 0)
        await page.getByText(/server may take about a minute to wake/).waitFor()
        assert.equal(posts, 0)
      })
      await check(
        `Anonymous example, CSP, MapLibre and contextual data label ${viewport.width}`,
        async () => {
          await page.getByTestId('recommendation').waitFor()
          await page.getByText('Example trip', { exact: true }).waitFor()
          await page.getByText(/forecast locations · ready/).waitFor()
          await page.waitForFunction(
            () =>
              document.querySelector('[data-testid="operational-map"]')?.dataset.renderer ===
                'maplibre' &&
              document.querySelector('[data-testid="operational-map"]')?.dataset.visualReady ===
                'true',
          )
          assert.equal(posts, 0)
          const text = await page.locator('body').innerText()
          assert.ok(
            !/\b(demo|assessment|noncommercial|reviewer|experimental)\b/i.test(
              text.replaceAll('atlas-assessment-policy-v1.0.0', ''),
            ),
          )
          assert.equal(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
            true,
          )
          await page.screenshot({ path: path.join(output, `dispatch-${viewport.width}.png`) })
        },
      )
      await check(
        `All 49 positions, genuine frame contracts and immutable recommendation ${viewport.width}`,
        async () => {
          const analysis = await (
            await page.request.get(`${base}/api/v1/examples/complete/`)
          ).json()
          if (viewport.width === 1440) {
            for (const variable of ['wind', 'rain', 'snow'])
              for (let hour = 0; hour <= 48; hour++) {
                const response = await page.request.get(
                  `${base}/api/v1/analyses/${analysis.id}/frames/?hour=${hour}&variable=${variable}`,
                )
                assert.equal(response.status(), 200)
                const frame = await response.json()
                assert.equal(frame.hour, hour)
                assert.equal(frame.analysis_id, analysis.id)
                assert.equal(frame.sample_data, true)
              }
          }
          if (viewport.width === 390)
            await page.getByRole('link', { name: 'Forecast', exact: true }).click()
          const slider = page.getByRole('slider')
          await slider.focus()
          await slider.press('End')
          await page.getByRole('button', { name: 'Snow', exact: true }).click()
          await page.getByText(/Displayed: \+48h snow/).waitFor()
          assert.equal(await slider.inputValue(), '48')
          assert.ok(await page.getByText(/Unknown cells stay unclassified/).isVisible())
          assert.equal(analysis.recommendation.route_id, 'route-b')
          await slider.press('Home')
          await page.getByRole('button', { name: 'Wind', exact: true }).click()
          await page.getByText(/Displayed: \+0h wind/).waitFor()
        },
      )
      await check(`Live planning honestly restricted at the action ${viewport.width}`, async () => {
        if (viewport.width === 390)
          await page.getByRole('link', { name: 'Dispatch', exact: true }).click()
        await page.getByRole('button', { name: 'Plan Route', exact: true }).first().click()
        assert.equal(await page.getByLabel('Trip source').inputValue(), 'live')
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
      await check(`Sources, safety and normal driver briefing ${viewport.width}`, async () => {
        if (viewport.width === 390) {
          await page.getByRole('link', { name: 'Inspect', exact: true }).click()
          await page
            .getByRole('button', { name: /Inspect source intervals and assumptions/ })
            .click()
        } else await page.getByRole('button', { name: 'Sources', exact: true }).click()
        await page.getByText(/example trip uses illustrative route geometry/).waitFor()
        await page.getByText(/not live forecasts/).waitFor()
        await page.screenshot({ path: path.join(output, `sources-${viewport.width}.png`) })
        await page.keyboard.press('Escape')
        await page
          .getByRole('button', {
            name: viewport.width === 390 ? 'Summary' : 'Driver briefing',
            exact: true,
          })
          .click()
        await page.getByRole('heading', { name: 'Route B · recommended', exact: true }).waitFor()
        assert.ok(await page.getByText(/Review while parked/).isVisible())
        await page.screenshot({ path: path.join(output, `driver-${viewport.width}.png`) })
        await page.keyboard.press('Escape')
      })
      await check(
        `Reload reuses example without a code or creation POST ${viewport.width}`,
        async () => {
          const count = posts
          await page.reload()
          await page.getByTestId('recommendation').waitFor()
          assert.equal(posts, count)
          assert.equal(await page.getByLabel('Private reviewer access code').count(), 0)
          assert.deepEqual((await context.storageState()).origins, [])
        },
      )
      await context.close()
    }
    assert.deepEqual(results.errors, [])
    assert.deepEqual(results.external_requests, [])
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
