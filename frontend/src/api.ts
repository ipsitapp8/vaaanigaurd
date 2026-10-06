import type {
  AnalysisResponse,
  ApiError,
  HealthResponse,
  VerificationComplete,
  VerificationStart,
} from './types'

export interface ScenarioSummary {
  id: string
  title: string
  persona: string
  description: string
  expected_tier: string
  duration_s: number
}

export class ApiFailure extends Error {
  code: string
  hint: string
  status: number
  constructor(code: string, message: string, hint: string, status: number) {
    super(message)
    this.code = code
    this.hint = hint
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, init)
  } catch {
    throw new ApiFailure('network', 'Cannot reach the backend.', 'Is it running on port 8000?', 0)
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiError | null
    throw new ApiFailure(
      body?.error.code ?? 'http_error',
      body?.error.message ?? `Request failed (${res.status}).`,
      body?.error.hint ?? 'Try again.',
      res.status,
    )
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const post = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<HealthResponse>('/health'),
  scenarios: () => request<ScenarioSummary[]>('/scenarios'),
  runScenario: (id: string) => request<AnalysisResponse>(`/scenarios/${id}/run`, { method: 'POST' }),
  upload: (form: FormData) => request<AnalysisResponse>('/analyses', { method: 'POST', body: form }),
  analysis: (id: string) => request<AnalysisResponse>(`/analyses/${id}`),
  purge: (id: string) => request<void>(`/analyses/${id}`, { method: 'DELETE' }),
  startVerification: (id: string) =>
    request<VerificationStart>(`/analyses/${id}/verification`, { method: 'POST' }),
  completeVerification: (verificationId: string, body: VerificationComplete) =>
    request<AnalysisResponse>(`/verifications/${verificationId}/complete`, post(body)),
}

export const scenarioAudioUrl = (id: string) => `/api/scenarios/${id}/audio`
export const reportUrl = (id: string, format: 'json' | 'html') =>
  `/api/analyses/${id}/report?format=${format}`
