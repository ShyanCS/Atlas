import type { components } from './generated'

export type Analysis = components['schemas']['Analysis']
export type RouteCandidate = components['schemas']['Route']
export type Checkpoint = components['schemas']['Checkpoint']
export type Measurement = components['schemas']['Measurement']
export type WeatherFrame = components['schemas']['Frame']
export type TripInput = components['schemas']['AnalysisInputRequest']
export type Scenario = components['schemas']['Scenario']
export type Scenarios = components['schemas']['Scenarios']
export type Location = components['schemas']['Location']
export type RiskLevel = Checkpoint['overall_risk']
export type WeatherVariable = WeatherFrame['variable']
export type ApiErrorBody = components['schemas']['ErrorResponse']
