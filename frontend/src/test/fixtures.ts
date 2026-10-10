import completeJson from './fixtures/complete.json'
import partialJson from './fixtures/partial.json'
import noTravelJson from './fixtures/no-travel.json'
import scenariosJson from './fixtures/scenarios.json'
import windJson from './fixtures/wind-0.json'
import missingSnowJson from './fixtures/snow-48.json'
import { isAnalysis, isScenarios, isWeatherFrame } from '../api/validation'
import type { Analysis, Scenarios, WeatherFrame } from '../contracts/types'

function requireAnalysis(value: unknown): Analysis {
  if (!isAnalysis(value))
    throw new Error('Authored sample analysis fixture no longer matches the API contract.')
  return value
}
function requireFrame(value: unknown): WeatherFrame {
  if (!isWeatherFrame(value))
    throw new Error('Authored sample frame fixture no longer matches the API contract.')
  return value
}
function requireScenarios(value: unknown): Scenarios {
  if (!isScenarios(value))
    throw new Error('Authored scenarios fixture no longer matches the API contract.')
  return value
}

// Captured solely from the local Django authored SAMPLE DATA API; no provider geometry.
export const completeAnalysis = requireAnalysis(completeJson)
export const partialAnalysis = requireAnalysis(partialJson)
export const noTravelAnalysis = requireAnalysis(noTravelJson)
// A unit-only mixed eligibility snapshot composed from the authored local scenarios.
export const mixedEligibilityAnalysis: Analysis = {
  ...completeAnalysis,
  routes: completeAnalysis.routes.map((route) =>
    route.code === 'C' ? noTravelAnalysis.routes.find((blocked) => blocked.code === 'C')! : route,
  ),
}
export const scenariosFixture = requireScenarios(scenariosJson)
export const windFrame = requireFrame(windJson)
export const missingSnowFrame = requireFrame(missingSnowJson)
