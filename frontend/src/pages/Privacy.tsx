import { useCallback, useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { api, ApiFailure, type PrivacyManifest } from '../api'
import { btn, Card, ErrorState, Skeleton } from '../ui'

export default function Privacy() {
  const [m, setM] = useState<PrivacyManifest | null>(null)
  const [error, setError] = useState<ApiFailure | null>(null)
  const [confirm, setConfirm] = useState(false)
  const [done, setDone] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setError(null)
    api.manifest().then(setM).catch((e: ApiFailure) => setError(e))
  }, [])
  useEffect(load, [load])

  const purgeAll = async () => {
    setBusy(true)
    try { setDone((await api.purgeAll()).purged) } catch (e) { setError(e as ApiFailure) } finally { setBusy(false); setConfirm(false) }
  }

  if (error && !m) return <ErrorState message={error.message} hint={error.hint} onRetry={load} />
  if (!m) return <Skeleton className="h-64" />

  return (
    <div className="space-y-4">
      <p className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">{m.synthetic_data_notice}</p>
      <Card title="What is collected, why, and for how long">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500"><tr><th className="py-1 pr-4">Collected</th><th className="pr-4">Why</th><th>Retention</th></tr></thead>
            <tbody>{m.collected.map((c) => (
              <tr key={c.item} className="border-t border-slate-800 align-top"><td className="py-2 pr-4 font-medium text-slate-200">{c.item}</td><td className="pr-4 text-slate-300">{c.why}</td><td className="text-slate-400">{c.retention}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Never collected"><ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">{m.never_collected.map((x) => <li key={x}>{x}</li>)}</ul></Card>
        <Card title="Limits"><ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">{m.disclaimers.map((x) => <li key={x}>{x}</li>)}</ul></Card>
      </div>
      <Card title="Purge demo data">
        <p className="text-sm text-slate-400">{m.purge} You can also purge a single analysis from its detail page.</p>
        {done !== null && <p role="status" className="mt-2 text-sm text-emerald-300">Purged {done} analyses. Each purge was written to the audit log.</p>}
        {error && <div className="mt-2"><ErrorState message={error.message} hint={error.hint} /></div>}
        <div className="mt-3 flex gap-2">
          {confirm ? (<><button onClick={purgeAll} disabled={busy} className={`${btn} border-red-500/60 text-red-200`}><Trash2 className="h-4 w-4" /> Confirm: purge all</button><button onClick={() => setConfirm(false)} className={btn}>Cancel</button></>)
            : <button onClick={() => setConfirm(true)} className={btn}><Trash2 className="h-4 w-4" /> Purge all demo data</button>}
        </div>
      </Card>
    </div>
  )
}
