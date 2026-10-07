import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck, ShieldX } from 'lucide-react'
import { api, ApiFailure } from '../api'
import type { AuditEntryOut, AuditVerifyResult } from '../types'
import { btnPrimary, Card, ErrorState, Skeleton, Spinner } from '../ui'

export default function Audit() {
  const [rows, setRows] = useState<AuditEntryOut[] | null>(null)
  const [error, setError] = useState<ApiFailure | null>(null)
  const [result, setResult] = useState<AuditVerifyResult | null>(null)
  const [checking, setChecking] = useState(false)

  const load = useCallback(() => {
    setError(null)
    api.audit().then(setRows).catch((e: ApiFailure) => setError(e))
  }, [])
  useEffect(load, [load])

  const verify = async () => {
    setChecking(true); setError(null)
    try { setResult(await api.auditVerify()) } catch (e) { setError(e as ApiFailure) } finally { setChecking(false) }
  }

  if (error && !rows) return <ErrorState message={error.message} hint={error.hint} onRetry={load} />
  if (!rows) return <Skeleton className="h-64" />

  return (
    <div className="space-y-4">
      <Card title="Hash-chained audit log" right={<button onClick={verify} disabled={checking} className={btnPrimary}><ShieldCheck className="h-4 w-4" /> Verify chain integrity</button>}>
        <p className="text-sm text-slate-400">Each entry stores sha256(previous hash + payload). Editing, deleting or reordering an entry breaks every hash after it. Entries hold ids and outcomes only, never transcripts or personal data.</p>
        {checking && <div className="mt-2"><Spinner label="Recomputing the chain…" /></div>}
        {result && (
          <div role="status" className={`mt-3 flex items-center gap-2 rounded border p-2 text-sm ${result.valid ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200' : 'border-red-500/40 bg-red-500/10 text-red-200'}`}>
            {result.valid ? <ShieldCheck className="h-4 w-4" /> : <ShieldX className="h-4 w-4" />}
            {result.valid ? `Chain valid: ${result.entries} entries recomputed.` : `Chain BROKEN at entry #${result.broken_at}.`}
          </div>
        )}
        {error && <div className="mt-2"><ErrorState message={error.message} hint={error.hint} /></div>}
      </Card>
      <Card>
        {rows.length === 0 ? (
          <div className="py-8 text-center text-slate-400"><p>No audit entries yet.</p><Link to="/live" className="mt-2 inline-block text-sky-300 hover:underline">Run a demo scenario →</Link></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500"><tr><th className="py-1 pr-3">#</th><th className="pr-3">Time</th><th className="pr-3">Actor</th><th className="pr-3">Action</th><th className="pr-3">Analysis</th><th className="pr-3">Detail</th><th>Entry hash</th></tr></thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.seq} className={`border-t border-slate-800 align-top ${result && !result.valid && e.seq === result.broken_at ? 'bg-red-500/10' : ''}`}>
                    <td className="py-1.5 pr-3 font-mono text-slate-400">{e.seq}</td>
                    <td className="pr-3 text-slate-400">{new Date(e.ts).toLocaleTimeString()}</td>
                    <td className="pr-3">{e.actor}</td>
                    <td className="pr-3 font-mono text-xs">{e.action}</td>
                    <td className="pr-3 font-mono text-xs">{e.analysis_id ? <Link to={`/analyses/${e.analysis_id}`} className="text-sky-300 hover:underline">{e.analysis_id}</Link> : '—'}</td>
                    <td className="pr-3 font-mono text-[11px] text-slate-500">{JSON.stringify(e.detail)}</td>
                    <td className="font-mono text-[11px] text-slate-500" title={e.entry_hash}>{e.entry_hash.slice(0, 12)}…</td>
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
