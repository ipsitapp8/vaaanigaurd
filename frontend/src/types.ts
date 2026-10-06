// Mirrors backend/app/models (SPEC section H, I). Keep in sync by hand.

export type SignalName = 'voice' | 'scam' | 'urgency' | 'financial' | 'identity' | 'context'
export type SignalSource = 'model' | 'heuristic' | 'rules' | 'simulated' | 'fallback' | 'cached'
export type Tier = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type Channel = 'pstn' | 'voip' | 'whatsapp' | 'unknown'
export type PaymentRail = 'UPI' | 'IMPS' | 'NEFT' | 'RTGS' | 'wallet'
export type AnalysisStatus =
  | 'analyzed'
  | 'verifying'
  | 'released'
  | 'held'
  | 'blocked'
  | 'in_review'
  | 'closed'
export type VerificationOutcome = 'pending' | 'pass' | 'fail' | 'no_response'
export type ReviewDecision = 'pending' | 'approve' | 'reject' | 'escalate'
export type TransactionState = 'pending' | 'held' | 'released' | 'blocked'
export type VerificationMethod =
  | 'in_app_warning'
  | 'codeword'
  | 'out_of_band_device_confirm'
  | 'independent_callback'
  | 'dynamic_challenge'
  | 'trusted_contact'
  | 'second_approver'
  | 'manual_security_review'
  | 'cooling_off_hold'
  | 'end_call_and_call_official_number'

export interface Evidence {
  kind: string
  text: string
  span: [number, number] | null
  weight: number
}

export interface SignalResult {
  name: SignalName
  score: number // 0-100, higher = riskier
  confidence: number // 0-1; 0 = unavailable
  source: SignalSource
  evidence: Evidence[]
  latency_ms: number
}

export interface CallMetadata {
  caller_number_masked: string
  in_directory: boolean
  directory_name: string | null
  channel: Channel
  started_at: string // ISO datetime
}

export interface TransactionContext {
  account_id: string
  amount_inr: number | null
  beneficiary_id: string | null
  beneficiary_is_new: boolean
  beneficiary_age_days: number | null
  typical_amount_inr: number
  activity_window: [number, number] // hours
  recent_txn_count_1h: number
  payment_rail: PaymentRail | null
}

export interface SegmentScore {
  t_start: number
  t_end: number
  text_redacted: string
  cumulative_score: number
  tier: Tier
}

// --- Persisted tables (SQLModel) ---

export interface Analysis {
  id: string
  created_at: string
  scenario_id: string | null
  is_synthetic: boolean
  audio_sha256: string
  audio_retained: boolean
  audio_expires_at: string | null
  language: string | null
  transcript_redacted: string
  signals_json: string
  rules_triggered_json: string
  segments_json: string
  score: number
  tier: Tier
  coverage: number
  explanation_json: string
  status: AnalysisStatus
}

export interface Verification {
  id: string
  analysis_id: string
  methods_json: string
  reason: string
  outcome: VerificationOutcome
  completed_at: string | null
  actor: string
}

export interface ReviewItem {
  id: string
  analysis_id: string
  priority: number
  decision: ReviewDecision
  analyst_note: string | null
  decided_at: string | null
}

export interface AuditEntry {
  seq: number
  ts: string
  actor: string
  action: string
  analysis_id: string | null
  payload_hash: string
  prev_hash: string
  entry_hash: string // sha256(prev_hash + payload)
}

export interface EnrolledVoice {
  id: string
  display_name: string
  consent_ref: string
  // embedding_encrypted is never sent to the client
}

// --- API (section I) ---

export type ComponentStatus = 'loaded' | 'fallback' | 'unavailable' | 'not_loaded'

export interface HealthResponse {
  status: 'ok'
  version: string
  device: 'cpu' | 'cuda'
  components: {
    asr: ComponentStatus
    deepfake_model: ComponentStatus
    speaker: ComponentStatus
    zero_shot: ComponentStatus
    db: ComponentStatus
  }
  force_fallback: boolean
}

export interface RuleTriggered {
  id: string
  effect: string
  reason: string
}

export interface Highlight {
  start_char: number
  end_char: number
  category: string
}

export interface RecommendedAction {
  tier: Tier
  methods: VerificationMethod[]
  why: string
  transaction_state: TransactionState
}

export interface AnalysisResponse {
  id: string
  score: number
  tier: Tier
  coverage: number
  signals: SignalResult[]
  contributions: Record<string, number>
  rules_triggered: RuleTriggered[]
  reasons: string[]
  recommended_action: RecommendedAction
  segments: SegmentScore[]
  transcript_redacted: string
  highlights: Highlight[]
  language: string | null
  latency_ms: Record<string, number>
  components: Record<string, { source: SignalSource; note?: string }>
  is_synthetic: boolean
}

export interface ApiError {
  error: { code: string; message: string; hint: string }
}
