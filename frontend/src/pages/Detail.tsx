import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { FileJson, FileText, Info, Trash2 } from 'lucide-react'
import { api, ApiFailure, reportUrl } from '../api'
import { CategoryLegend, RiskGauge, Transcript } from '../components/RiskViz'
import { TransactionState, VerificationPanel } from '../components/VerificationPanel'
import type { AnalysisResponse, SignalResult } from '../types'
import { btn, Card, ErrorState, inr, SIGNAL_LABELS, Skeleton, SOURCE_LABELS, TierChip } from '../ui'

const PIE_COLORS = ['#38bdf8', '#a78bfa', '#f59e0b', '#ef4444', '#34d399', '#f472b6']

function lowConfidenceReason(s: SignalResult): string {
  if (s.confidence === 0) return 'Unavailable: this signal is excluded from the score.'
  const q = s.evidence.find((e) => e.kind === 'voice_quality' || e.kind === 'voice_model_unavailable')
  return q ? q.text : 'Low confidence: this signal counts for less in the weighted score.'
}

function SignalBar({ s, pct }: { s: SignalResult; pct: number | undefined }) {
  const faded = s.confidence < 0.5
  return (
    <li className="space-y-1">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-slate-200">{SIGNAL_LABELS[s.name] ?? s.name}</span>
        <span className="flex items-center gap-2 font-mono text-xs text-slate-400">
          <span className="rounded border border-slate-700 px-1.5 py-0.5 font-sans text-[10px] uppercase text-slate-400">{SOURCE_LABELS[s.source] ?? s.source}</span>
          {s.confidence === 0 ? 'n/a' : `${Math.round(s.score)}`} · conf {s.confidence.toFixed(2)}{pct != null && ` · ${pct}%`}
        </span>
      </div>
      <div className="h-2 rounded bg-slate-800" title={faded ? lowConfidenceReason(s) : undefined}>
        <div className="h-2 rounded bg-sky-400" style={{ width: `${s.confidence === 0 ? 0 : s.score}%`, opacity: Math.max(0.25, s.confidence) }} />
      </div>
      {faded && <div className="flex items-start gap-1 text-xs text-slate-500"><Info className="mt-0.5 h-3 w-3 shrink-0" /> {lowConfidenceReason(s)}</div>}
      {s.evidence.length > 0 && (
        <details className="text-xs text-slate-400">
          <summary className="cursor-pointer text-slate-500 hover:text-slate-300">Evidence ({s.evidence.length})</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">{s.evidence.map((e, i) => <li key={i}>{e.text}</li>)}</ul>
        </details>
      )}
    </li>
  )
}

function Hash({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="break-all font-mono text-xs text-slate-300">{value ?? '—'}</div>
    </div>
  )
}

export default function Detail() {
  const { id = '' } = useParams()
  const [a, setA] = useState<AnalysisResponse | null>(null)
  const [error, setError] = useState<ApiFailure | null>(null)
  const [confirmPurge, setConfirmPurge] = useState(false)
  const [purged, setPurged] = useState(false)
  const [purging, setPurging] = useState(false)

  const load = useCallback(() => {
    setError(null)
    setA(null)
    api.analysis(id).then(setA).catch((e: ApiFailure) => setError(e))
  }, [id])
  useEffect(load, [load])

  const purge = async () => {
    setPurging(true)
    try { await api.purge(id); setPurged(true); setA(null) } catch (e) { setError(e as ApiFailure) } finally { setPurging(false); setConfirmPurge(false) }
  }

  if (purged || error?.status === 410) {
    return (
      <Card><div className="space-y-2 py-6 text-center">
        <p className="text-slate-200">This analysis was purged.</p>
        <p className="text-sm text-slate-400">Audio, transcript, segments and signals were deleted. A hash-only tombstone and the audit entry remain.</p>
        <Link to="/live" className="text-sm text-sky-300 hover:underline">Run a demo scenario →</Link>
      </div></Card>
    )
  }
  if (error) return <ErrorState message={error.status === 404 ? 'No analysis with this id.' : error.message} hint={error.hint} onRetry={error.status === 404 ? undefined : load} />
  if (!a) return <div className="grid gap-4 lg:grid-cols-2"><Skeleton className="h-64" /><Skeleton className="h-64" /><Skeleton className="h-48" /><Skeleton className="h-48" /></div>

  const pie = Object.entries(a.contributions).filter(([, v]) => v > 0).map(([k, v]) => ({ name: SIGNAL_LABELS[k] ?? k, value: v }))
  const t = a.transaction

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold text-slate-100">Analysis <span className="font-mono text-slate-400">{a.id}</span></h1>
        <TierChip tier={a.tier} />
        <span className="rounded border border-slate-700 px-2 py-0.5 font-mono text-xs text-slate-300">status: {a.status}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          <a href={reportUrl(a.id, 'html')} target="_blank" rel="noreferrer" className={btn}><FileText className="h-4 w-4" /> Report (HTML)</a>
          <a href={reportUrl(a.id, 'json')} target="_blank" rel="noreferrer" className={btn}><FileJson className="h-4 w-4" /> Report (JSON)</a>
          {confirmPurge ? (
            <>
              <button onClick={purge} disabled={purging} className={`${btn} border-red-500/60 text-red-200`}><Trash2 className="h-4 w-4" /> Confirm purge</button>
              <button onClick={() => setConfirmPurge(false)} className={btn}>Cancel</button>
            </>
          ) : (
            <button onClick={() => setConfirmPurge(true)} className={btn}><Trash2 className="h-4 w-4" /> Purge</button>
          )}
        </div>
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[repeat(3,minmax(0,1fr))]">
        <Card title="Risk"><RiskGauge score={a.score} tier={a.tier} />
          <p className="mt-3 text-center text-xs text-slate-500">Coverage {Math.round(a.coverage * 100)}% of signal weight available</p>
          <p className="mt-1 text-center text-sm text-slate-400">Transaction: <TransactionState state={a.recommended_action.transaction_state} />{t?.amount_inr != null && <> · {inr(t.amount_inr)}</>}</p>
        </Card>

        <Card title="Signals" className="lg:col-span-2">
          <ul className="space-y-3">{a.signals.map((s) => <SignalBar key={s.name} s={s} pct={a.contributions[s.name]} />)}</ul>
          <p className="mt-3 text-xs text-slate-500">Bar length = score, opacity = confidence. The voice model is not validated on Indian telephony audio and a voice score alone can never push risk above MEDIUM.</p>
        </Card>

        <Card title="Why this score">
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-200">{a.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
          <h3 className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wider text-slate-400">Rules triggered</h3>
          {a.rules_triggered.length === 0 ? <p className="text-sm text-slate-500">None</p> : (
            <ul className="space-y-1 text-sm">{a.rules_triggered.map((r, i) => (
              <li key={i}><span className="font-mono text-orange-300">{r.id}</span> <span className="font-mono text-xs text-slate-500">({r.effect})</span> <span className="text-slate-300">{r.reason}</span></li>
            ))}</ul>
          )}
        </Card>

        <Card title="Contribution">
          {pie.length === 0 ? <p className="text-sm text-slate-500">No contributing signals.</p> : (
            <div className="h-56"><ResponsiveContainer><PieChart>
              <Pie data={pie} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={2} stroke="none">
                {pie.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', fontSize: 12 }} formatter={(v) => `${v}%`} />
            </PieChart></ResponsiveContainer></div>
          )}
          <ul className="mt-1 space-y-0.5 text-xs text-slate-400">{pie.map((p, i) => (
            <li key={p.name}><span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />{p.name} {p.value}%</li>
          ))}</ul>
        </Card>

        <div className="space-y-4">
          <VerificationPanel analysis={a} onUpdated={setA} />
        </div>

        <Card title="Transcript (redacted)" className="lg:col-span-2">
          {a.segments.length === 0 ? <p className="text-sm text-slate-400">No transcript. {a.components.asr?.note}</p> : (
            <><Transcript segments={a.segments} highlights={a.highlights} visibleCount={a.segments.length} /><CategoryLegend highlights={a.highlights} /></>
          )}
        </Card>

        <Card title="Components and latency">
          <ul className="space-y-1 text-sm">{Object.entries(a.components).map(([k, c]) => (
            <li key={k}><span className="font-medium text-slate-200">{k}</span> <span className="rounded border border-slate-700 px-1 text-[10px] uppercase text-slate-400">{SOURCE_LABELS[c.source] ?? c.source}</span>
              {c.note && <div className="text-xs text-slate-500">{c.note}</div>}</li>
          ))}</ul>
          <p className="mt-3 font-mono text-xs text-slate-400">{Object.entries(a.latency_ms).map(([k, v]) => `${k} ${v} ms`).join(' · ')}</p>
        </Card>

        <Card title="Evidence hashes" className="lg:col-span-3">
          <div className="grid gap-3 md:grid-cols-2">
            <Hash label="Audio SHA-256" value={a.audio_sha256} />
            <Hash label="Analysis SHA-256 (at creation)" value={a.analysis_sha256} />
          </div>
          <p className="mt-2 text-xs text-slate-500">Audio retained: {a.audio_retained ? `yes, until ${a.audio_expires_at}` : 'no (deleted after analysis)'} · Created {a.created_at ?? '—'}</p>
        </Card>
      </div>
    </div>
  )
}
