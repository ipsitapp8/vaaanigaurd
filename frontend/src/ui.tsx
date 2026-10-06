import type { ReactNode } from 'react'
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react'
import type { Tier } from './types'

export const TIER_STYLE: Record<Tier, { text: string; border: string; bg: string; hex: string }> = {
  LOW: { text: 'text-emerald-300', border: 'border-emerald-500/50', bg: 'bg-emerald-500/10', hex: '#10b981' },
  MEDIUM: { text: 'text-amber-300', border: 'border-amber-500/50', bg: 'bg-amber-500/10', hex: '#f59e0b' },
  HIGH: { text: 'text-orange-300', border: 'border-orange-500/50', bg: 'bg-orange-500/10', hex: '#f97316' },
  CRITICAL: { text: 'text-red-300', border: 'border-red-500/50', bg: 'bg-red-500/10', hex: '#ef4444' },
}

export function tierOf(score: number): Tier {
  return score >= 80 ? 'CRITICAL' : score >= 60 ? 'HIGH' : score >= 30 ? 'MEDIUM' : 'LOW'
}

export function TierChip({ tier }: { tier: Tier }) {
  const s = TIER_STYLE[tier]
  return (
    <span className={`rounded border px-2 py-0.5 font-mono text-xs font-semibold ${s.border} ${s.bg} ${s.text}`}>
      {tier}
    </span>
  )
}

export const inr = (n: number | null | undefined) =>
  n == null ? '—' : `₹${n.toLocaleString('en-IN')}`

export function Card({ title, children, className = '', right }: { title?: string; children: ReactNode; className?: string; right?: ReactNode }) {
  return (
    <section className={`rounded-lg border border-slate-800 bg-slate-900/50 p-4 ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</h2>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-slate-800/70 ${className}`} />
}

export function Spinner({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-400">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </span>
  )
}

export function ErrorState({ message, hint, onRetry }: { message: string; hint?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm">
      <div className="flex items-center gap-2 font-medium text-red-300">
        <AlertTriangle className="h-4 w-4" /> {message}
      </div>
      {hint && <div className="text-slate-400">{hint}</div>}
      {onRetry && (
        <button onClick={onRetry} className="mt-1 flex items-center gap-1 rounded border border-red-500/40 px-2 py-1 text-red-200 hover:bg-red-500/10">
          <RefreshCw className="h-3 w-3" /> Retry
        </button>
      )}
    </div>
  )
}

export const btn =
  'inline-flex items-center justify-center gap-1.5 rounded-md border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-100 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50'
export const btnPrimary =
  'inline-flex items-center justify-center gap-1.5 rounded-md border border-emerald-500/60 bg-emerald-600/20 px-3 py-1.5 text-sm font-medium text-emerald-200 hover:bg-emerald-600/30 disabled:cursor-not-allowed disabled:opacity-50'

export const SIGNAL_LABELS: Record<string, string> = {
  voice: 'Voice authenticity',
  scam: 'Scam language',
  urgency: 'Urgency / coercion',
  financial: 'Financial / credential request',
  identity: 'Identity / channel',
  context: 'Transaction context',
}

export const METHOD_LABELS: Record<string, string> = {
  in_app_warning: 'In-app warning',
  codeword: 'Codeword (out-of-band)',
  out_of_band_device_confirm: 'Registered-device confirmation',
  independent_callback: 'Independent callback',
  dynamic_challenge: 'Dynamic challenge',
  trusted_contact: 'Trusted-contact callback',
  second_approver: 'Second approver',
  manual_security_review: 'Manual security review',
  cooling_off_hold: 'Cooling-off hold',
  end_call_and_call_official_number: 'End call and call the official number',
}

export const SOURCE_LABELS: Record<string, string> = {
  model: 'Real ML',
  heuristic: 'Heuristic',
  rules: 'Rules',
  simulated: 'Simulated',
  fallback: 'Fallback',
  cached: 'Cached',
}
