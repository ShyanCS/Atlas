/* Local integration checks. No provider requests or credentials are used. */
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const { chromium } = require('@playwright/test')

const root = path.resolve(__dirname, '../..')
const frontendUrl = process.env.ATLAS_FRONTEND_URL || 'http://127.0.0.1:5173'
assert.ok(
  ['127.0.0.1', 'localhost'].includes(new URL(frontendUrl).hostname),
  'Browser tests are local only',
)
const evidenceRoot = path.join(root, 'docs/implementation/evidence')
const output = path.resolve(evidenceRoot, process.env.ATLAS_BROWSER_EVIDENCE_SUBDIR || 'browser')
const evidenceRelative = path.relative(evidenceRoot, output)
assert.ok(
  !evidenceRelative.startsWith('..') && !path.isAbsolute(evidenceRelative),
  'Evidence must stay within the workspace evidence directory',
)
fs.mkdirSync(output, { recursive: true })
const results = {
  started_at: new Date().toISOString(),
  environment: {
    browser: 'Installed Google Chrome, headless',
    rendering: 'SwiftShader software WebGL; not physical GPU validation',
    frontend: frontendUrl,
    backend: process.env.ATLAS_BACKEND_URL || 'http://127.0.0.1:8000',
    sample_only: true,
  },
  checks: [],
  errors: [],
  console: [],
  external_requests: [],
  timings: [],
}
let browser
async function check(name, fn) {
  const start = performance.now()
  try {
    await fn()
    results.checks.push({
      name,
      status: 'PASS',
      milliseconds: Math.round(performance.now() - start),
    })
  } catch (error) {
    results.checks.push({ name, status: 'FAIL', error: error.message })
    throw error
  }
}
async function context(viewport, extras = {}) {
  const ctx = await browser.newContext({ viewport, reducedMotion: 'reduce', ...extras })
  await ctx.route('**/*', async (route) => {
    const url = route.request().url()
    if (/^(https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\/|data:|blob:)/.test(url))
      await route.continue()
    else {
      results.external_requests.push(url)
      await route.abort()
    }
  })
  const page = await ctx.newPage()
  page.on('pageerror', (error) => results.errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning')
      results.console.push({ type: message.type(), text: message.text() })
  })
  return { ctx, page }
}
async function open(page) {
  await page.goto(frontendUrl, { waitUntil: 'networkidle' })
}
async function analyzeDefault(page) {
  const start = performance.now()
  const response = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/analyses/') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Analyze default sample', exact: true }).click()
  const api = await response
  assert.equal(api.status(), 201)
  const analysis = await api.json()
  await page.getByTestId('recommendation').waitFor()
  await page.getByText(/sample cells ·/).waitFor()
  results.timings.push({
    operation: 'POST sample + render first frame',
    milliseconds: Math.round(performance.now() - start),
    analysis_status: analysis.status,
    routes: analysis.routes.length,
  })
  return analysis
}
async function screenshot(page, name) {
  await page.waitForFunction(
    () => document.querySelector('[data-testid="operational-map"]')?.dataset.visualReady === 'true',
  )
  await page.screenshot({ path: path.join(output, name) })
}
async function submitScenario(page, scenario) {
  await page.getByRole('button', { name: 'Edit sample trip', exact: true }).click()
  await page.getByLabel('Labeled sample scenario', { exact: true }).selectOption(scenario)
  const response = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/analyses/') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Analyze sample trip', exact: true }).click()
  const api = await response
  assert.equal(api.status(), 201)
  const result = await api.json()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  return result
}

;(async () => {
  try {
    browser = await chromium.launch({
      ...(process.env.ATLAS_BROWSER_EXECUTABLE
        ? { executablePath: process.env.ATLAS_BROWSER_EXECUTABLE }
        : { channel: process.env.ATLAS_BROWSER_CHANNEL || 'chrome' }),
      headless: true,
      args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'],
    })
    results.environment.browser_version = browser.version()
    const desktop = await context({ width: 1440, height: 900 })
    const page = desktop.page
    await check('Initial state clearly labeled sample, no fabricated analysis', async () => {
      await open(page)
      assert.equal(await page.getByTestId('recommendation').count(), 0)
      assert.ok(await page.getByText('SAMPLE DATA', { exact: true }).isVisible())
      await screenshot(page, 'dispatch-empty.desktop.png')
    })
    let analysis
    await check('Actual Django analysis and first frame, stable backend preference', async () => {
      analysis = await analyzeDefault(page)
      assert.equal(analysis.mode, 'sample')
      assert.equal(analysis.sample_data, true)
      assert.equal(analysis.recommendation.route_id, 'route-b')
      assert.equal(analysis.routes.length, 3)
      await page
        .getByTestId('operational-map')
        .locator('[aria-label="Arrival-time risk legend"]')
        .waitFor()
      await page.waitForFunction(
        () => {
          const map = document.querySelector('[data-testid="operational-map"]')
          return map?.dataset.renderer === 'maplibre' && map?.dataset.visualReady === 'true'
        },
        null,
        { timeout: 8000 },
      )
      await screenshot(page, 'dispatch-canvas.desktop.png')
      assert.ok(
        await page.locator('.map-canvas').evaluate((el) => el.getBoundingClientRect().height > 250),
        'Operational map container must have visible height',
      )
    })
    await check(
      'Inspection selection cannot change recommendation; checkpoint selection consistent',
      async () => {
        await page.getByTestId('route-C').click()
        assert.equal(await page.getByTestId('route-C').getAttribute('aria-pressed'), 'true')
        assert.ok(
          await page.getByRole('heading', { name: 'Route B preferred.', exact: true }).isVisible(),
        )
        await page
          .getByRole('button', { name: 'Open accessible checkpoint list', exact: true })
          .click()
        await page.getByRole('button', { name: 'Inspect CP1 on Route C', exact: true }).click()
        assert.ok(await page.getByRole('heading', { name: 'CP1', exact: true }).isVisible())
        await page.getByTestId('route-B').click()
      },
    )
    await check(
      'Keyboard 0–48-hour timeline, separate raw/arrival legends, Unknown snowfall',
      async () => {
        const slider = page.getByRole('slider', {
          name: 'Requested forecast hour offset',
          exact: true,
        })
        await slider.focus()
        await slider.press('End')
        await page.getByRole('button', { name: 'Snow', exact: true }).click()
        await page.getByText(/Displayed: \+48h snow/).waitFor()
        assert.equal(await slider.inputValue(), '48')
        assert.ok(await page.getByLabel('Raw forecast variable legend').isVisible())
        assert.equal(await page.getByLabel('Arrival-time risk legend').count(), 0)
        assert.ok(await page.getByText(/Unknown cells stay unclassified/).isVisible())
        assert.ok(
          await page.getByRole('heading', { name: 'Route B preferred.', exact: true }).isVisible(),
        )
        await screenshot(page, 'forecast-unknown.desktop.png')
        await slider.press('Home')
        await page.getByRole('button', { name: 'Wind', exact: true }).click()
        await page.getByText(/Displayed: \+0h wind/).waitFor()
        await page.getByRole('button', { name: 'Risk at arrival', exact: true }).click()
      },
    )
    await check('Native dialog keyboard focus and Escape return', async () => {
      const trigger = page.getByRole('button', { name: 'Edit sample trip', exact: true })
      await trigger.focus()
      await trigger.press('Enter')
      assert.ok(await page.getByRole('dialog').isVisible())
      for (let i = 0; i < 24; i++) {
        await page.keyboard.press('Tab')
        assert.ok(
          await page.evaluate(() =>
            document.querySelector('dialog')?.contains(document.activeElement),
          ),
        )
      }
      await page.keyboard.press('Escape')
      assert.equal(await page.getByRole('dialog').count(), 0)
      assert.ok(await trigger.evaluate((element) => element === document.activeElement))
      await trigger.click()
      await page.getByLabel('Cargo load · pounds', { exact: true }).fill('30000')
      await page.keyboard.press('Escape')
      assert.equal(
        await page.getByText('Previous analysis · draft changed', { exact: true }).count(),
        0,
      )
      assert.ok(
        await page.getByRole('heading', { name: 'Route B preferred.', exact: true }).isVisible(),
      )
    })
    await check(
      'Incomplete forecast coverage withholds recommendation and shows Unknown',
      async () => {
        const result = await submitScenario(page, 'partial')
        assert.equal(result.recommendation.route_id, null)
        assert.equal(result.recommendation.state, 'unverified')
        assert.ok(
          await page
            .getByRole('heading', { name: 'Recommendation withheld.', exact: true })
            .isVisible(),
        )
        await screenshot(page, 'coverage-partial.desktop.png')
      },
    )
    await check('Known No Travel never becomes an eligible recommendation', async () => {
      const result = await submitScenario(page, 'no-travel')
      assert.equal(result.recommendation.route_id, null)
      assert.equal(result.recommendation.state, 'blocked')
      assert.equal(
        result.routes.every((route) => route.eligible === false),
        true,
      )
      assert.ok(
        await page
          .getByRole('heading', { name: 'Recommendation withheld.', exact: true })
          .isVisible(),
      )
      assert.ok(
        await page
          .getByTestId('route-A')
          .getByText('No Travel', { exact: true })
          .first()
          .isVisible(),
      )
      await screenshot(page, 'no-travel.desktop.png')
    })
    await check(
      'Ambiguous/nonexistent local time requires backend resolution; input retained',
      async () => {
        await page.getByRole('button', { name: 'Edit sample trip', exact: true }).click()
        await page.getByLabel('Local departure', { exact: true }).fill('2026-11-01T01:30')
        let response = page.waitForResponse(
          (response) =>
            response.url().endsWith('/api/v1/analyses/') && response.request().method() === 'POST',
        )
        await page.getByRole('button', { name: 'Analyze sample trip', exact: true }).click()
        let api = await response
        assert.equal(api.status(), 400)
        assert.equal((await api.json()).error.code, 'DEPARTURE_TIME_AMBIGUOUS')
        assert.ok(await page.getByRole('dialog').isVisible())
        assert.equal(
          await page.getByLabel('Local departure', { exact: true }).inputValue(),
          '2026-11-01T01:30',
        )
        await page.getByLabel('Local departure', { exact: true }).fill('2026-03-08T02:30')
        response = page.waitForResponse(
          (response) =>
            response.url().endsWith('/api/v1/analyses/') && response.request().method() === 'POST',
        )
        await page.getByRole('button', { name: 'Analyze sample trip', exact: true }).click()
        api = await response
        assert.equal(api.status(), 400)
        assert.equal((await api.json()).error.code, 'DEPARTURE_TIME_NONEXISTENT')
        await screenshot(page, 'time-validation.desktop.png')
        await page.keyboard.press('Escape')
      },
    )
    await check(
      'Backend analysis failure retains prior immutable result; loading and quota states',
      async () => {
        await submitScenario(page, 'complete')
        const before = await page.locator('.crumb').innerText()
        const { promise: failureGate, resolve: releaseFailure } = Promise.withResolvers()
        const delayedFailure = async (route) => {
          await failureGate
          await route.fulfill({
            status: 429,
            contentType: 'application/json',
            headers: { 'Retry-After': '10' },
            body: JSON.stringify({
              error: {
                code: 'SAMPLE_ADMISSION_LIMIT',
                message: 'Local test quota exhausted; previous analysis retained.',
                details: {},
              },
              request_id: 'test-only',
            }),
          })
        }
        await page.route('**/api/v1/analyses/', delayedFailure)
        await page.getByRole('button', { name: 'Edit sample trip', exact: true }).click()
        await page.getByRole('button', { name: 'Analyze sample trip', exact: true }).click()
        try {
          assert.ok(
            await page.getByRole('button', { name: 'Analyzing sample…', exact: true }).isDisabled(),
          )
        } finally {
          releaseFailure()
        }
        await page
          .getByRole('dialog')
          .getByText('Local test quota exhausted; previous analysis retained.', { exact: true })
          .waitFor()
        assert.equal(await page.locator('.crumb').innerText(), before)
        await screenshot(page, 'quota-error.desktop.png')
        await page.unroute('**/api/v1/analyses/', delayedFailure)
        await page.keyboard.press('Escape')
      },
    )
    await check('Reduced motion computed styles and simulated WebGL context loss', async () => {
      assert.equal(
        await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches),
        true,
      )
      assert.equal(
        await page
          .locator('.btn')
          .first()
          .evaluate((element) => getComputedStyle(element).transitionDuration),
        '0s',
      )
      await page
        .locator('.maplibregl-canvas')
        .evaluate((canvas) =>
          canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true })),
        )
      await page.waitForFunction(
        () =>
          document.querySelector('[data-testid="operational-map"]')?.dataset.renderer ===
          'fallback',
      )
      assert.ok(
        await page.getByRole('heading', { name: 'Route B preferred.', exact: true }).isVisible(),
      )
      await screenshot(page, 'context-loss.desktop.png')
    })
    await desktop.ctx.close()
    const mobile = await context({ width: 390, height: 844 }, { isMobile: true, hasTouch: true })
    await check(
      'Mobile 390×844 layout, all routes reachable through same-state dialog',
      async () => {
        await open(mobile.page)
        await analyzeDefault(mobile.page)
        await screenshot(mobile.page, 'dispatch-canvas.mobile.png')
        assert.equal(
          await mobile.page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
          true,
        )
        assert.equal(
          await mobile.page
            .locator('.workspace')
            .evaluate((element) => element.scrollWidth <= element.clientWidth),
          true,
        )
        await mobile.page.getByRole('link', { name: 'Forecast', exact: true }).click()
        const forecast = await mobile.page.locator('#forecast').boundingBox()
        const navigation = await mobile.page
          .getByRole('navigation', { name: 'Mobile dispatch navigation' })
          .boundingBox()
        assert.ok(forecast && navigation && forecast.y + forecast.height <= navigation.y)
        assert.ok(navigation && Math.abs(navigation.y + navigation.height - 844) <= 1)
        assert.equal(await mobile.page.evaluate(() => window.scrollY), 0)
        assert.equal(await mobile.page.evaluate(() => document.activeElement.id), 'forecast')
        await screenshot(mobile.page, 'forecast.mobile.png')
        await mobile.page.getByRole('link', { name: 'Dispatch', exact: true }).click()
        await mobile.page.getByRole('button', { name: '3 routes', exact: true }).click()
        assert.equal(await mobile.page.getByRole('dialog').getByTestId('route-A').count(), 1)
        assert.equal(await mobile.page.getByRole('dialog').getByTestId('route-C').count(), 1)
        await mobile.page.getByRole('dialog').getByTestId('route-A').click()
        assert.equal(await mobile.page.getByTestId('route-A').getAttribute('aria-pressed'), 'true')
        await mobile.page
          .getByRole('button', { name: 'Open accessible checkpoint list', exact: true })
          .click()
        await mobile.page
          .getByRole('button', { name: 'Inspect CP1 on Route A', exact: true })
          .click()
        await mobile.page.getByRole('link', { name: 'Inspect', exact: true }).click()
        assert.ok(
          await mobile.page
            .getByRole('heading', { name: 'Route B preferred.', exact: true })
            .isVisible(),
        )
        await mobile.page
          .getByRole('button', { name: /Inspect source intervals and assumptions/ })
          .scrollIntoViewIfNeeded()
        const rect = await mobile.page
          .getByRole('button', { name: /Inspect source intervals and assumptions/ })
          .boundingBox()
        const nav = await mobile.page
          .getByRole('navigation', { name: 'Mobile dispatch navigation' })
          .boundingBox()
        assert.ok(rect && nav && rect.y + rect.height <= nav.y)
        assert.ok(nav && Math.abs(nav.y + nav.height - 844) <= 1)
        assert.equal(await mobile.page.evaluate(() => window.scrollY), 0)
        await screenshot(mobile.page, 'checkpoint-inspector.mobile.png')
        await mobile.page.getByRole('button', { name: 'Summary', exact: true }).click()
        assert.ok(
          await mobile.page
            .getByRole('heading', { name: 'Route B preferred in this sample', exact: true })
            .isVisible(),
        )
        await screenshot(mobile.page, 'driver-summary.mobile.png')
      },
    )
    await mobile.ctx.close()
    const fallback = await context({ width: 1440, height: 900 })
    await fallback.page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext
      HTMLCanvasElement.prototype.getContext = function (type, ...args) {
        return /webgl/.test(type) ? null : original.call(this, type, ...args)
      }
    })
    await check(
      'WebGL failure preserves route cards, diagram and keyboard/list alternatives',
      async () => {
        await open(fallback.page)
        await analyzeDefault(fallback.page)
        assert.equal(
          await fallback.page.getByTestId('operational-map').getAttribute('data-renderer'),
          'fallback',
        )
        await fallback.page
          .getByRole('button', { name: 'Inspect Route A in simplified map', exact: true })
          .focus()
        await fallback.page.keyboard.press('Enter')
        assert.equal(
          await fallback.page.getByTestId('route-A').getAttribute('aria-pressed'),
          'true',
        )
        assert.ok(
          await fallback.page
            .getByRole('heading', { name: 'Route B preferred.', exact: true })
            .isVisible(),
        )
        await screenshot(fallback.page, 'webgl-fallback.desktop.png')
      },
    )
    await fallback.ctx.close()
    await check('No external network resources or uncaught browser errors', async () => {
      assert.equal(results.external_requests.length, 0)
      assert.equal(results.errors.length, 0)
    })
  } catch (error) {
    results.fatal = error.stack
    process.exitCode = 1
  } finally {
    if (browser) await browser.close()
    results.completed_at = new Date().toISOString()
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2))
    console.log(JSON.stringify(results, null, 2))
  }
})()
