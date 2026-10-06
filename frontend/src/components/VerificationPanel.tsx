import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, ClipboardList, PhoneOff, ShieldAlert, XCircle } from 'lucide-react'
import { api, ApiFailure } from '../api'
import type { AnalysisResponse, VerificationStart } from '../types'
import { btn, ErrorState, METHOD_LABELS, Spinner, TierChip } from '../ui'

const FINAL = ['released', 'blocked', 'closed']

const STATE_TEXT: Record<string, { label: string; cls: string }> = {
  pending: { label: 'Pending', cls: 'text-slate-300' },
  held: { label: 'Held', cls: 'text-orange-300' },
  released: { label: 'Released', cls: 'text-emerald-300' },
  blocked: { label: 'Blocked', cls: 'text-red-300' },
}

export function TransactionState({ state }: { state: string }) {
  const s = STATE_TEXT[state] ?? STATE_TEXT.pending
  return <span className={`font-semibold ${s.cls}`}>{s.label}</span>
}

/**
 * Picks up the verification the backend selected for this analysis, explains why, and lets the demo
 * user simulate the outcome. The outcome re-scores the analysis server-side.
 */
export function VerificationPanel({ analysis, onUpdated }: { analysis: AnalysisResponse; onUpdated: (a: AnalysisResponse) => void }) {
  const [start, setStart] = useState<VerificationStart | null>(null)
  const [error, setError] = useState<ApiFailure | null>(null)
  const [busy, setBusy] = useState(false)
  const [scoreBefore, setScoreBefore] = useState<number | null>(null)

  const verified = analysis.rules_triggered.find((r) => r.id.startsWith('VERIFY_'))
  const finalised = FINAL.includes(analysis.status)
  const needed = analysis.tier !== 'LOW' || verified != null

  const begin = useCallback(() => {
    setError(null)
    api.startVerification(analysis.id).then(setStart).catch((e: ApiFailure) => setError(e))
  }, [analysis.id])

  useEffect(() => {
    if (needed && !finalised && !verified) begin()
  }, [needed, finalised, verified, begin])

  const complete = async (outcome: 'pass' | 'fail' | 'no_response') => {
    if (!start) return
    setBusy(true)
    setError(null)
    setScoreBefore(analysis.score)
    try {
      onUpdated(await api.completeVerification(start.verification_id, { outcome, actor: 'demo-user' }))
    } catch (e) {
      setError(e as ApiFailure)
    } finally {
      setBusy(false)
    }
  }

  if (!needed) {
    return (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm text-slate-300">
        <div className="mb-1 flex items-center gap-2 font-medium text-emerald-300"><CheckCircle2 className="h-4 w-4" /> No extra verification needed</div>
        Low risk: the call continues without friction and the interaction is logged.
      </div>
    )
  }

  const who = analysis.claimed_identity ?? 'The person'
  return (
    <div className="animate-[slidein_350ms_ease] rounded-lg border border-orange-500/40 bg-slate-900/70 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-semibold text-slate-100">
          <ShieldAlert className="h-4 w-4 text-orange-400" /> Verification
        </div>
        <TierChip tier={analysis.tier} />
      </div>

      {error && error.code !== 'analysis_finalised' && <ErrorState message={error.message} hint={error.hint} onRetry={start ? undefined : begin} />}
      {!start && !error && !verified && <Spinner label="Selecting the least disruptive sufficient method…" />}

      {start && !verified && (
        <>
          <div className="mb-3 rounded border border-slate-700 bg-slate-950/60 p-3 text-sm">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">Why this verification?</div>
            <p className="text-slate-200">{analysis.recommended_action.why}</p>
          </div>
          <ol className="mb-3 space-y-2">
            {start.methods.map((m, i) => (
              <li key={m} className="rounded border border-slate-700 p-2 text-sm">
                <div className="font-medium text-slate-100">{i + 1}. {METHOD_LABELS[m] ?? m}</div>
                <div className="text-slate-400">{start.instructions[m]}</div>
              </li>
            ))}
          </ol>
          <div className="text-xs text-slate-500">Simulated channels (demo only): choose what happens.</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button disabled={busy} onClick={() => complete('pass')} className={btn}><CheckCircle2 className="h-4 w-4 text-emerald-400" /> Simulate: {who} confirms</button>
            <button disabled={busy} onClick={() => complete('fail')} className={btn}><XCircle className="h-4 w-4 text-red-400" /> Simulate: {who} denies</button>
            <button disabled={busy} onClick={() => complete('no_response')} className={btn}><PhoneOff className="h-4 w-4 text-amber-400" /> Simulate: no response</button>
          </div>
        </>
      )}

      {verified && (
        <div className="rounded border border-slate-700 bg-slate-950/60 p-3 text-sm">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">Re-scored result</div>
          <p className="text-slate-200">{verified.reason}</p>
          <p className="mt-2 font-mono text-slate-300">
            {scoreBefore != null && <>{scoreBefore} → </>}{analysis.score} · <TierChip tier={analysis.tier} /> · transaction{' '}
            <TransactionState state={analysis.recommended_action.transaction_state} />
          </p>
          {analysis.review_id && (
            <p className="mt-2 flex items-center gap-1 text-xs text-slate-400"><ClipboardList className="h-3.5 w-3.5" /> In the analyst review queue (item <span className="font-mono">{analysis.review_id}</span>).</p>
          )}
          <Link to={`/analyses/${analysis.id}`} className="mt-2 inline-block text-xs text-sky-300 hover:underline">Open evidence and audit trail →</Link>
        </div>
      )}
    </div>
  )
}
