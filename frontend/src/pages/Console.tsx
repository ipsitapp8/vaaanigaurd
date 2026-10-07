import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, ClipboardList, IndianRupee, Lock, Timer } from 'lucide-react'
import { api, ApiFailure, type Stats } from '../api'
import type { AnalysisSummary } from '../types'
import { btnPrimary, Card, ErrorState, inr, Skeleton, TierChip } from '../ui'

function Kpi({ icon, label, value, hint }: { icon: React.ReactNode; label: string; value: string; hint?: string }) {
  return (
    <Card>
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-400">{icon} {label}</div>
      <div className="mt-2 font-mono text-2xl font-semibold text-slate-100">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </Card>
  )
}

export default function Console() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [rows, setRows] = useState<AnalysisSummary[] | null>(null)
  const [error, setError] = useState<ApiFailure | null>(null)

  const load = useCallback(() => {
    setError(null)
    Promise.all([api.stats(), api.analyses(15)]).then(([s, r]) => { setStats(s); setRows(r) }).catch((e: ApiFailure) => setError(e))
  }, [])
  useEffect(load, [load])

  if (error) return <ErrorState message={error.message} hint={error.hint} onRetry={load} />
  if (!stats || !rows) return <div className="space-y-4"><div className="grid grid-cols-2 gap-4 lg:grid-cols-5">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24" />)}</div><Skeleton className="h-64" /></div>

  return (
    <div className="space-y-4">
      <p className="text-slate-300">VaaniGuard decides <b>how much independent verification</b> a call needs before money moves. Detectors are fallible, so no voice score alone can push risk above MEDIUM.</p>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi icon={<Activity className="h-4 w-4" />} label="Analyses today" value={String(stats.analyses_today)} />
        <Kpi icon={<Lock className="h-4 w-4" />} label="Held transactions" value={String(stats.held_transactions)} />
        <Kpi icon={<IndianRupee className="h-4 w-4" />} label="Protected (synthetic)" value={inr(stats.protected_inr)} hint="Blocked transfers" />
        <Kpi icon={<Timer className="h-4 w-4" />} label="Median latency" value={stats.median_latency_ms == null ? '—' : `${(stats.median_latency_ms / 1000).toFixed(1)} s`} />
        <Link to="/review"><Kpi icon={<ClipboardList className="h-4 w-4" />} label="Review queue" value={String(stats.review_pending)} hint="Open the queue →" /></Link>
      </div>

      <Card title="Recent analyses" right={<Link to="/live" className={btnPrimary}>Run a demo scenario</Link>}>
        {rows.length === 0 ? (
          <div className="py-8 text-center text-slate-400">
            <p>No analyses yet.</p>
            <Link to="/live" className="mt-2 inline-block text-sky-300 hover:underline">Run a demo scenario →</Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500"><tr><th className="py-1 pr-3">Time</th><th className="pr-3">Id</th><th className="pr-3">Scenario</th><th className="pr-3">Score</th><th className="pr-3">Tier</th><th>Status</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-slate-800">
                    <td className="py-1.5 pr-3 text-slate-400">{new Date(r.created_at).toLocaleTimeString()}</td>
                    <td className="pr-3 font-mono">{r.purged ? <span className="text-slate-500">{r.id} (purged)</span> : <Link to={`/analyses/${r.id}`} className="text-sky-300 hover:underline">{r.id}</Link>}</td>
                    <td className="pr-3 text-slate-300">{r.scenario_id ?? 'upload'}</td>
                    <td className="pr-3 font-mono">{r.score}</td>
                    <td className="pr-3"><TierChip tier={r.tier} /></td>
                    <td className="font-mono text-xs text-slate-400">{r.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
