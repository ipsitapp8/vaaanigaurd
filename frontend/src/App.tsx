import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { RefreshCw, ShieldCheck } from 'lucide-react'
import { api } from './api'
import Detail from './pages/Detail'
import Live from './pages/Live'
import type { ComponentStatus, HealthResponse } from './types'

const PILL_LABELS: Record<keyof HealthResponse['components'], string> = {
  asr: 'ASR',
  deepfake_model: 'Deepfake',
  speaker: 'Speaker',
  zero_shot: 'Zero-shot',
  db: 'DB',
}

const PILL_STYLE: Record<ComponentStatus, string> = {
  loaded: 'border-emerald-500/40 text-emerald-300',
  fallback: 'border-amber-500/40 text-amber-300',
  unavailable: 'border-red-500/40 text-red-300',
  not_loaded: 'border-slate-600 text-slate-400',
}

function StatusPill({ label, status }: { label: string; status: ComponentStatus }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 font-mono text-xs ${PILL_STYLE[status]}`}
      title={`${label}: ${status.replace('_', ' ')}`}
    >
      {label} · {status.replace('_', ' ')}
    </span>
  )
}

function Header() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(() => {
    setError(false)
    api.health().then(setHealth).catch(() => setError(true))
  }, [])

  // Poll so the pills flip from "not loaded" to "loaded" once models finish warming up.
  useEffect(() => {
    load()
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [load])

  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-800 bg-slate-900/60 px-6 py-3">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-emerald-400" />
        <span className="text-lg font-semibold tracking-tight text-slate-100">VaaniGuard</span>
      </div>
      <nav className="flex gap-3 text-sm">
        <NavLink to="/live" className={({ isActive }) => (isActive ? 'text-slate-100' : 'text-slate-400 hover:text-slate-200')}>
          Live Monitor
        </NavLink>
      </nav>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {health &&
          (Object.keys(PILL_LABELS) as (keyof HealthResponse['components'])[]).map((k) => (
            <StatusPill key={k} label={PILL_LABELS[k]} status={health.components[k]} />
          ))}
        {error && (
          <button
            onClick={load}
            className="flex items-center gap-1 rounded-full border border-red-500/40 px-2 py-0.5 text-xs text-red-300 hover:bg-red-500/10"
          >
            <RefreshCw className="h-3 w-3" /> Backend unreachable · retry
          </button>
        )}
        <span className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 font-mono text-xs font-semibold text-amber-300">
          SYNTHETIC DEMO DATA
        </span>
      </div>
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-950 pb-10">
        <Header />
        <main className="mx-auto max-w-7xl p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/live" replace />} />
            <Route path="/live" element={<Live />} />
            <Route path="/analyses/:id" element={<Detail />} />
            <Route path="*" element={<Navigate to="/live" replace />} />
          </Routes>
        </main>
        <footer className="fixed inset-x-0 bottom-0 border-t border-slate-800 bg-slate-950/90 px-6 py-1.5 text-center text-xs text-slate-500">
          Prototype · synthetic data only · scores are risk indicators, not proof · a human decides on
          high-impact actions
        </footer>
      </div>
    </BrowserRouter>
  )
}
