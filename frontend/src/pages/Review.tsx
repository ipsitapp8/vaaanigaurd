import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ArrowUpRight, X } from 'lucide-react'
import { api, ApiFailure } from '../api'
import { useRole } from '../role'
import type { AnalysisResponse, ReviewItemOut } from '../types'
import { btn, Card, ErrorState, inr, Skeleton, TierChip } from '../ui'

function EvidencePanel({ item, onDone }: { item: ReviewItemOut; onDone: () => void }) {
  const [a, setA] = useState<AnalysisResponse | null>(null)
  const [err, setErr] = useState<ApiFailure | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const { role } = useRole()

  useEffect(() => {
    setA(null); setErr(null); setNote('')
    api.analysis(item.analysis_id).then(setA).catch((e: ApiFailure) => setErr(e))
  }, [item.analysis_id])

  const decide = async (decision: 'approve' | 'reject' | 'escalate') => {
    setBusy(true); setErr(null)
    try { await api.reviewDecision(item.id, { decision, note }); onDone() } catch (e) { setErr(e as ApiFailure) } finally { setBusy(false) }
  }

  if (!a) return err ? <ErrorState message={err.message} hint={err.hint} /> : <Skeleton className="h-64" />
  const analyst = role === 'analyst'
  return (
    <Card title="Evidence">
      <div className="mb-2 flex items-center gap-2"><TierChip tier={a.tier} /><span className="font-mono text-lg">{a.score}</span><span className="text-sm text-slate-400">status {a.status} · {inr(a.transaction?.amount_inr)}</span></div>
      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-200">{a.reasons.slice(0, 5).map((r, i) => <li key={i}>{r}</li>)}</ul>
      <h3 className="mb-1 mt-3 text-xs font-semibold uppercase text-slate-400">Signals</h3>
      <ul className="grid grid-cols-2 gap-x-4 text-sm text-slate-300">{a.signals.map((s) => <li key={s.name} className="flex justify-between"><span>{s.name}</span><span className="font-mono text-slate-400">{s.confidence === 0 ? 'n/a' : Math.round(s.score)} · {s.confidence.toFixed(2)}</span></li>)}</ul>
      <h3 className="mb-1 mt-3 text-xs font-semibold uppercase text-slate-400">Redacted transcript</h3>
      <p className="max-h-32 overflow-y-auto rounded bg-slate-950/60 p-2 text-sm text-slate-300">{a.transcript_redacted || 'No transcript.'}</p>
      <p className="mt-2 break-all font-mono text-[11px] text-slate-500">audio sha256 {a.audio_sha256}</p>
      <Link to={`/analyses/${a.id}`} className="mt-1 inline-block text-xs text-sky-300 hover:underline">Full detail and audit trail →</Link>

      <div className="mt-4 border-t border-slate-800 pt-3">
        {!analyst && <p className="mb-2 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">Decisions need the Analyst role (demo switch in the header; production would use bank IAM/SSO + RBAC).</p>}
        <label className="text-sm text-slate-300">Analyst note (required)
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={2000} className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 p-2 text-sm" placeholder="Why this decision?" />
        </label>
        {err && <div className="mt-2"><ErrorState message={err.message} hint={err.hint} /></div>}
        <div className="mt-2 flex flex-wrap gap-2">
          <button disabled={!analyst || busy || !note.trim()} onClick={() => decide('approve')} className={btn}><Check className="h-4 w-4 text-emerald-400" /> Approve (release)</button>
          <button disabled={!analyst || busy || !note.trim()} onClick={() => decide('reject')} className={btn}><X className="h-4 w-4 text-red-400" /> Reject (block)</button>
          <button disabled={!analyst || busy || !note.trim()} onClick={() => decide('escalate')} className={btn}><ArrowUpRight className="h-4 w-4 text-amber-400" /> Escalate</button>
        </div>
      </div>
    </Card>
  )
}

export default function Review() {
  const [items, setItems] = useState<ReviewItemOut[] | null>(null)
  const [error, setError] = useState<ApiFailure | null>(null)
  const [sel, setSel] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    api.reviewQueue().then((r) => { setItems(r); setSel((cur) => (cur && r.some((i) => i.id === cur) ? cur : (r[0]?.id ?? null))) }).catch((e: ApiFailure) => setError(e))
  }, [])
  useEffect(load, [load])

  if (error) return <ErrorState message={error.message} hint={error.hint} onRetry={load} />
  if (!items) return <Skeleton className="h-64" />
  if (items.length === 0) return (
    <Card><div className="py-10 text-center text-slate-400"><p>The review queue is empty.</p><p className="text-sm">CRITICAL interactions land here.</p>
      <Link to="/live" className="mt-2 inline-block text-sky-300 hover:underline">Run a demo scenario →</Link></div></Card>
  )
  const current = items.find((i) => i.id === sel) ?? items[0]
  return (
    <div className="grid gap-4 lg:grid-cols-[repeat(5,minmax(0,1fr))]">
      <Card title={`Queue (${items.length})`} className="lg:col-span-2">
        <ul className="space-y-2">
          {items.map((i) => (
            <li key={i.id}>
              <button onClick={() => setSel(i.id)} className={`w-full rounded border p-2 text-left text-sm ${i.id === current.id ? 'border-sky-500/60 bg-sky-500/10' : 'border-slate-700 hover:bg-slate-800/50'}`}>
                <div className="flex items-center justify-between"><span className="font-mono text-xs text-slate-400">{i.analysis_id}</span><span className="flex items-center gap-2">{i.tier && <TierChip tier={i.tier} />}<span className="font-mono">{i.score}</span></span></div>
                <div className="mt-1 text-slate-200">{i.claimed_identity ?? 'Unknown caller'} · {inr(i.amount_inr)}</div>
                <div className="text-xs text-slate-500">priority {i.priority} · {i.decision === 'escalate' ? 'escalated' : 'pending'} · {i.status}</div>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      <div className="lg:col-span-3"><EvidencePanel item={current} onDone={load} /></div>
    </div>
  )
}
