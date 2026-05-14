export type MethodType =
  | 'official_api'
  | 'unofficial_api'
  | 'http_requests'
  | 'headless_browser'
  | 'classical_browser'

export type ResultType = 'data' | 'engagement' | 'posting' | 'auth' | 'monitor'

export interface AlgorithmDef {
  id: string
  label: string
  parent: string
  rootParent: string
  platform: string
  platformDisplay: string
  resultType: ResultType
  compatibleMethods: MethodType[]
  description: string
  code: string
}

export const ALGORITHM_CATALOGUE: AlgorithmDef[] = []

export const METHOD_LABELS: Record<MethodType, string> = {
  official_api:      'Official API',
  unofficial_api:    'Unofficial API',
  http_requests:     'HTTP Requests',
  headless_browser:  'Headless Browser',
  classical_browser: 'Classical Browser',
}

export const METHOD_DESC: Record<MethodType, string> = {
  official_api:      'Rate-limited but stable. Requires API keys.',
  unofficial_api:    'Faster, no API key. Higher ban risk.',
  http_requests:     'Raw session-based HTTP. No browser overhead.',
  headless_browser:  'Playwright / Puppeteer. No visible window.',
  classical_browser: 'Selenium with real browser. Most human-like.',
}

export const RESULT_COLOURS: Record<ResultType, string> = {
  data:       'bg-blue-900/50 text-blue-300',
  engagement: 'bg-emerald-900/50 text-emerald-300',
  posting:    'bg-purple-900/50 text-purple-300',
  auth:       'bg-amber-900/50 text-amber-300',
  monitor:    'bg-gray-800 text-gray-400',
}

export const PLATFORMS = ['reddit'] as const

export function algorithmsForPlatform(platform: string): AlgorithmDef[] {
  return ALGORITHM_CATALOGUE.filter(a => a.platform === platform.toLowerCase())
}

export function algorithmsForMethod(method: MethodType): AlgorithmDef[] {
  return ALGORITHM_CATALOGUE.filter(a => a.compatibleMethods.includes(method))
}
