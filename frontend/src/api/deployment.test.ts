import { afterEach, expect, it, vi } from 'vitest'
import { AtlasApi } from './client'
import { getAssessmentAccessCode, setAssessmentAccessCode } from './access'

afterEach(() => setAssessmentAccessCode(''))
it('accepts an explicit HTTPS assessment API and uses a tab-memory bearer code', async () => {
  setAssessmentAccessCode('authored-reviewer-code-abcdefghijklmnopqrstuvwxyz')
  const fetcher = vi
    .fn<typeof fetch>()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ status: 'ok', assessment_access_required: true, live_available: false }),
      ),
    )
  await new AtlasApi('https://atlas.onrender.com/api/v1', fetcher).getHealth()
  expect(fetcher.mock.calls[0]?.[0]).toBe('https://atlas.onrender.com/api/v1/health/')
  expect(fetcher.mock.calls[0]?.[1]?.headers).toMatchObject({
    Authorization: `Bearer ${getAssessmentAccessCode()}`,
  })
  expect(fetcher.mock.calls[0]?.[1]?.credentials).toBe('omit')
})
it.each([
  'http://atlas.onrender.com/api/v1',
  'https://key:secret@atlas.onrender.com/api/v1',
  'https://atlas.onrender.com/api/v1?key=secret',
  '//atlas.onrender.com/api/v1',
])('rejects unsafe endpoint %s', (url) => {
  expect(() => new AtlasApi(url)).toThrow()
})
