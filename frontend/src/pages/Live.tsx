import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { FastForward, Phone, Play, Upload } from 'lucide-react'
import { api, ApiFailure, scenarioAudioUrl, type ScenarioSummary } from '../api'
import { CustomerView } from '../components/CustomerView'
import { Recorder } from '../components/Recorder'
import { CategoryLegend, RiskGauge, RiskTimeline, Transcript } from '../components/RiskViz'
import { TransactionState, VerificationPanel } from '../components/VerificationPanel'
import type { AnalysisResponse, Tier, TransactionContext } from '../types'
import { btn, btnPrimary, Card, ErrorState, inr, Skeleton, Spinner, TierChip, tierOf } from '../ui'

const verified0 = (a: AnalysisResponse) => a.rules_triggered.some((r) => r.id.startsWith('VERIFY_'))
const TIER_ORDER: Tier[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

function CallCard({ a }: { a: AnalysisResponse }) {
  const m = a.call_metadata
  return (
    <Card title="Call">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-slate-500">Caller</dt>
        <dd className="font-mono">{m?.caller_number_masked ?? '—'}</dd>
        <dt className="text-slate-500">Channel</dt>
        <dd className="uppercase">{m?.channel ?? '—'}</dd>
        <dt className="text-slate-500">In directory</dt>
        <dd>{m ? (m.in_directory ? `Yes${m.directory_name ? ` (${m.directory_name})` : ''}` : 'No') : '—'}</dd>
        <dt className="text-slate-500">Claims to be</dt>
        <dd>{a.claimed_identity ?? 'Not stated'}</dd>
        <dt className="text-slate-500">Language</dt>
        <dd>{a.language ?? '—'}</dd>
      </dl>
    </Card>
  )
}

function TransactionBar({ a, state }: { a: AnalysisResponse; state: string }) {
  const t = a.transaction
  if (!t || t.amount_inr == null) {
    return <Card title="Transaction"><p className="text-sm text-slate-400">No pending transaction in this context.</p></Card>
  }
  return (
    <Card title="Transaction (simulated)">
      <p className="text-sm text-slate-200">
        <span className="font-semibold">{inr(t.amount_inr)}</span>
        {t.payment_rail ? ` via ${t.payment_rail}` : ''} to{' '}
        <span className={t.beneficiary_is_new ? 'font-semibold text-amber-300' : ''}>
          {t.beneficiary_is_new ? `NEW beneficiary${t.beneficiary_age_days != null ? ` (${t.beneficiary_age_days} d old)` : ''}` : 'known beneficiary'}
        </span>
      </p>
      <p className="mt-1 text-sm text-slate-400">Typical for this account: {inr(t.typical_amount_inr)} · State: <TransactionState state={state} /></p>
    </Card>
  )
}

export default function Live() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[] | null>(null)
  const [listError, setListError] = useState<ApiFailure | null>(null)
  const [selected, setSelected] = useState<string>('')
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<ApiFailure | null>(null)

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const [initialTier, setInitialTier] = useState<Tier>('LOW')
  const [audioSrc, setAudioSrc] = useState<string | null>(null)
  const [time, setTime] = useState(0)
  const [ended, setEnded] = useState(false)
  const [customer, setCustomer] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const [amount, setAmount] = useState('')
  const [newBeneficiary, setNewBeneficiary] = useState(true)

  const audioRef = useRef<HTMLAudioElement>(null)
  const objectUrl = useRef<string | null>(null)
  const lastTier = useRef<Tier>('LOW')

  const loadScenarios = useCallback(() => {
    setListError(null)
    api.scenarios().then((s) => { setScenarios(s); setSelected((cur) => cur || s[0]?.id || '') }).catch((e: ApiFailure) => setListError(e))
  }, [])
  useEffect(loadScenarios, [loadScenarios])

  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current) }, [])

  const show = (res: AnalysisResponse, src: string) => {
    setAnalysis(res)
    setInitialTier(res.tier)
    setTime(0)
    setEnded(false)
    setToast(null)
    lastTier.current = 'LOW'
    setAudioSrc(src)
  }

  const run = async (go: () => Promise<[AnalysisResponse, string]>) => {
    setRunning(true)
    setRunError(null)
    try {
      const [res, src] = await go()
      show(res, src)
    } catch (e) {
      setRunError(e as ApiFailure)
    } finally {
      setRunning(false)
    }
  }

  const runScenario = () => run(async () => [await api.runScenario(selected), scenarioAudioUrl(selected)])

  const onUpload = (file: File) =>
    run(async () => {
      const form = new FormData()
      form.append('audio', file)
      const amt = Number(amount.replace(/,/g, ''))
      if (amt > 0) {
        const ctx: TransactionContext = {
          account_id: 'DEMO-0001', amount_inr: amt, beneficiary_id: 'demo_beneficiary', beneficiary_is_new: newBeneficiary,
          beneficiary_age_days: newBeneficiary ? 1 : 400, typical_amount_inr: 60000, activity_window: [9, 19], recent_txn_count_1h: 0, payment_rail: 'UPI',
        }
        form.append('context', JSON.stringify(ctx))
      }
      const res = await api.upload(form)
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = URL.createObjectURL(file)
      return [res, objectUrl.current]
    })

  useEffect(() => {
    if (audioSrc) audioRef.current?.play().catch(() => undefined) // autoplay may be blocked; the player controls remain
  }, [audioSrc])

  // --- derived live state ---
  const segments = analysis?.segments ?? []
  const visible = segments.filter((s) => s.t_start <= time || ended)
  const shownCount = analysis && (verified0(analysis) || ended) ? segments.length : visible.length
  const shownChars = segments.slice(0, shownCount).reduce((n, s) => n + s.text_redacted.length + 1, 0)
  const noSegments = analysis != null && segments.length === 0
  const verified = analysis?.rules_triggered.some((r) => r.id.startsWith('VERIFY_')) ?? false
  const liveScore = verified || noSegments ? (analysis?.score ?? 0) : (visible.at(-1)?.cumulative_score ?? 0)
  const liveTier = verified || noSegments ? (analysis?.tier ?? 'LOW') : tierOf(liveScore)
  const reached = analysis != null && (noSegments || verified || ended || TIER_ORDER.indexOf(liveTier) >= TIER_ORDER.indexOf(initialTier))

  useEffect(() => {
    if (!analysis) return
    if (liveTier !== lastTier.current && (liveTier !== 'LOW' || lastTier.current !== 'LOW')) {
      if (TIER_ORDER.indexOf(liveTier) > TIER_ORDER.indexOf(lastTier.current)) setToast(`Risk rose to ${liveTier}`)
    }
    lastTier.current = liveTier
  }, [liveTier, analysis])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(t)
  }, [toast])

  const txnState = analysis ? (reached || verified ? analysis.recommended_action.transaction_state : 'pending') : 'pending'

  const skipToEnd = () => {
    const el = audioRef.current
    if (el && Number.isFinite(el.duration)) { el.currentTime = el.duration; setEnded(true); setTime(el.duration) } else setEnded(true)
  }

  return (
    <div className="min-w-0 space-y-4">
      <Card title="Live call monitor" right={<span className="text-xs text-slate-500">Analysis runs server-side; playback reveals it in sync</span>}>
        {listError ? (
          <ErrorState message={listError.message} hint={listError.hint} onRetry={loadScenarios} />
        ) : !scenarios ? (
          <Skeleton className="h-10 w-full" />
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-64 flex-1 text-sm">
              <span className="mb-1 block text-xs text-slate-500">Demo scenario</span>
              <select value={selected} onChange={(e) => setSelected(e.target.value)} className="w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5">
                {scenarios.map((s) => (<option key={s.id} value={s.id}>{s.title} (expected {s.expected_tier})</option>))}
              </select>
            </label>
            <button className={btnPrimary} disabled={running || !selected} onClick={runScenario}><Play className="h-4 w-4" /> Run scenario</button>
            <div className="flex flex-wrap items-end gap-2 border-l border-slate-700 pl-3">
              <label className="text-sm"><span className="mb-1 block text-xs text-slate-500">Upload amount ₹ (optional)</span>
                <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="numeric" placeholder="e.g. 250000" className="w-32 rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5" /></label>
              <label className="flex items-center gap-1 pb-2 text-xs text-slate-400"><input type="checkbox" checked={newBeneficiary} onChange={(e) => setNewBeneficiary(e.target.checked)} /> new beneficiary</label>
              <Recorder disabled={running} onRecorded={(f) => void onUpload(f)} />
              <label className={`${btn} cursor-pointer ${running ? 'pointer-events-none opacity-50' : ''}`}>
                <Upload className="h-4 w-4" /> Upload audio
                <input type="file" accept="audio/*,.wav,.mp3,.m4a" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) void onUpload(f); e.target.value = '' }} />
              </label>
            </div>
          </div>
        )}
        {scenarios && selected && <p className="mt-2 text-xs text-slate-500">{scenarios.find((s) => s.id === selected)?.description}</p>}
        {running && <div className="mt-3"><Spinner label="Analysing (transcription + voice model)…" /></div>}
        {runError && <div className="mt-3"><ErrorState message={runError.message} hint={runError.hint} onRetry={selected ? runScenario : undefined} /></div>}
      </Card>

      {!analysis && !running && (
        <Card><div className="flex flex-col items-center gap-2 py-10 text-center text-slate-400">
          <Phone className="h-8 w-8 text-slate-600" />
          <p>No call analysed yet.</p>
          <p className="text-sm">Pick a demo scenario and press <b>Run scenario</b>, or upload your own audio.</p>
        </div></Card>
      )}

      {analysis?.components.cache && <p role="status" className="rounded border border-amber-500/50 bg-amber-500/10 p-2 text-sm font-semibold text-amber-200">{analysis.components.cache.note}</p>}
      {analysis && (
        <div className="grid min-w-0 gap-4 lg:grid-cols-[repeat(3,minmax(0,1fr))]">
          <div className="min-w-0 space-y-4">
            <CallCard a={analysis} />
            <Card title="Audio">
              <audio ref={audioRef} src={audioSrc ?? undefined} controls className="w-full"
                onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
                onSeeked={(e) => { setTime(e.currentTarget.currentTime); setEnded(false) }}
                onPlay={() => setEnded(false)}
                onEnded={() => setEnded(true)} />
              <button onClick={skipToEnd} className={`${btn} mt-2`}><FastForward className="h-4 w-4" /> Skip to end</button>
              <p className="mt-2 text-xs text-slate-500">Demo audio is placeholder TTS, not a real voice clone.</p>
            </Card>
            <TransactionBar a={analysis} state={txnState} />
          </div>

          <div className="min-w-0 space-y-4">
            <Card title="Risk">
              <RiskGauge score={liveScore} tier={liveTier} />
              <div className="mt-2"><RiskTimeline segments={verified ? segments : visible} time={ended ? null : time} /></div>
              {analysis.reasons.length > 0 && reached && (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">{analysis.reasons.slice(0, 4).map((r, i) => <li key={i}>{r}</li>)}</ul>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-4">
                <Link to={`/analyses/${analysis.id}`} className="text-sm text-sky-300 hover:underline">Full breakdown, evidence and audit →</Link>
                <label className="flex items-center gap-1.5 text-sm text-slate-400"><input type="checkbox" checked={customer} onChange={(e) => setCustomer(e.target.checked)} /> Customer view</label>
              </div>
              {customer && reached && <div className="mt-4"><CustomerView a={analysis} /></div>}
            </Card>
            {reached && analysis.tier !== 'LOW' && <VerificationPanel analysis={analysis} onUpdated={setAnalysis} />}
            {reached && analysis.tier === 'LOW' && !verified && <VerificationPanel analysis={analysis} onUpdated={setAnalysis} />}
          </div>

          <Card title="Transcript (redacted)" right={<TierChip tier={liveTier} />}>
            {noSegments ? <p className="text-sm text-slate-400">No transcript available. {analysis.components.asr?.note}</p> : (
              <>
                {visible.length === 0 && <p className="text-sm text-slate-500">Press play: the transcript appears as the call unfolds.</p>}
                <Transcript segments={segments} highlights={analysis.highlights} visibleCount={verified ? segments.length : visible.length} />
                <CategoryLegend highlights={analysis.highlights.filter((h) => h.end_char <= shownChars)} />
              </>
            )}
            {analysis.components.asr?.note && !noSegments && <p className="mt-3 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">{analysis.components.asr.note}</p>}
          </Card>
        </div>
      )}

      {toast && (
        <div role="status" className="fixed bottom-12 right-6 z-10 animate-[slidein_250ms_ease] rounded-md border border-orange-500/50 bg-slate-900 px-4 py-2 text-sm text-orange-200 shadow-lg">
          {toast}
        </div>
      )}
    </div>
  )
}
