import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Highlight, SegmentScore, Tier } from '../types'
import { TIER_STYLE, TierChip, tierOf } from '../ui'

/** Half-circle risk gauge 0-100; the arc length animates between scores. */
export function RiskGauge({ score, tier }: { score: number; tier: Tier }) {
  const r = 80
  const half = Math.PI * r
  const color = TIER_STYLE[tier].hex
  const arc = `M ${100 - r} 100 A ${r} ${r} 0 0 1 ${100 + r} 100`
  return (
    <div className="flex flex-col items-center" role="img" aria-label={`Risk score ${score} of 100, tier ${tier}`}>
      <svg viewBox="0 0 200 112" className="w-full max-w-xs">
        <path d={arc} fill="none" stroke="#1e293b" strokeWidth="14" strokeLinecap="round" />
        <path
          d={arc}
          fill="none"
          stroke={color}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={half}
          strokeDashoffset={half * (1 - Math.min(score, 100) / 100)}
          style={{ transition: 'stroke-dashoffset 600ms ease, stroke 400ms ease' }}
        />
        <text x="100" y="86" textAnchor="middle" className="fill-slate-100 font-mono text-4xl font-bold">
          {score}
        </text>
        <text x="100" y="106" textAnchor="middle" className="fill-slate-500 text-[9px]">
          RISK SCORE / 100
        </text>
      </svg>
      <TierChip tier={tier} />
    </div>
  )
}

export function RiskTimeline({ segments, time }: { segments: SegmentScore[]; time: number | null }) {
  const data = [{ t: 0, score: 0 }, ...segments.map((s) => ({ t: s.t_end, score: s.cumulative_score }))]
  const maxT = Math.max(...data.map((d) => d.t), time ?? 0, 1)
  return (
    <div className="h-48 w-full min-w-0">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <defs>
            <linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f97316" stopOpacity={0.5} />
              <stop offset="100%" stopColor="#f97316" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1e293b" vertical={false} />
          <XAxis dataKey="t" type="number" domain={[0, maxT]} tickFormatter={(v: number) => `${Math.round(v)}s`} stroke="#64748b" fontSize={11} />
          <YAxis domain={[0, 100]} ticks={[0, 30, 60, 80, 100]} stroke="#64748b" fontSize={11} />
          <ReferenceLine y={30} stroke="#f59e0b" strokeDasharray="3 3" strokeOpacity={0.5} />
          <ReferenceLine y={60} stroke="#f97316" strokeDasharray="3 3" strokeOpacity={0.5} />
          <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="3 3" strokeOpacity={0.5} />
          {time != null && <ReferenceLine x={Math.min(time, maxT)} stroke="#94a3b8" />}
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', fontSize: 12 }}
            formatter={(v) => [`${v} (${tierOf(Number(v))})`, 'Risk']}
            labelFormatter={(l) => `${Number(l).toFixed(1)} s`}
          />
          <Area type="stepAfter" dataKey="score" stroke="#f97316" strokeWidth={2} fill="url(#riskFill)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

const CATEGORY_STYLE: Record<string, string> = {
  credential: 'bg-red-500/25 text-red-200',
  account_threat: 'bg-red-500/20 text-red-200',
  remote_access: 'bg-red-500/25 text-red-200',
  urgency: 'bg-amber-500/25 text-amber-200',
  authority: 'bg-violet-500/25 text-violet-200',
  secrecy: 'bg-pink-500/25 text-pink-200',
  payment: 'bg-sky-500/25 text-sky-200',
  process_bypass: 'bg-orange-500/25 text-orange-200',
  emotional_lever: 'bg-fuchsia-500/25 text-fuchsia-200',
}

export function CategoryLegend({ highlights }: { highlights: Highlight[] }) {
  const cats = [...new Set(highlights.map((h) => h.category))]
  if (!cats.length) return null
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {cats.map((c) => (
        <span key={c} className={`rounded px-1.5 py-0.5 text-[11px] ${CATEGORY_STYLE[c] ?? 'bg-slate-700 text-slate-200'}`}>
          {c.replace('_', ' ')}
        </span>
      ))}
    </div>
  )
}

function renderWithHighlights(text: string, offset: number, highlights: Highlight[]) {
  const end = offset + text.length
  const inSeg = highlights
    .filter((h) => h.end_char > offset && h.start_char < end)
    .sort((a, b) => a.start_char - b.start_char)
  const parts: React.ReactNode[] = []
  let cursor = offset
  for (const h of inSeg) {
    const s = Math.max(h.start_char, cursor)
    const e = Math.min(h.end_char, end)
    if (e <= s) continue
    if (s > cursor) parts.push(text.slice(cursor - offset, s - offset))
    parts.push(
      <mark key={`${h.start_char}-${h.category}`} title={h.category.replace('_', ' ')} className={`rounded px-0.5 ${CATEGORY_STYLE[h.category] ?? 'bg-slate-600 text-slate-100'}`}>
        {text.slice(s - offset, e - offset)}
      </mark>,
    )
    cursor = e
  }
  if (cursor < end) parts.push(text.slice(cursor - offset))
  return parts
}

/** Redacted transcript, revealed segment by segment, with highlighted spans. Segments are joined by one space. */
export function Transcript({ segments, highlights, visibleCount }: { segments: SegmentScore[]; highlights: Highlight[]; visibleCount: number }) {
  const offsets = segments.reduce<number[]>((acc, _s, i) => [...acc, i === 0 ? 0 : acc[i - 1] + segments[i - 1].text_redacted.length + 1], [])
  const nodes = segments.map((s, i) => {
    if (i >= visibleCount) return null
    return (
      <p key={i} className="animate-[fadein_300ms_ease]">
        <span className="mr-2 font-mono text-[11px] text-slate-500">{s.t_start.toFixed(1)}s</span>
        {renderWithHighlights(s.text_redacted, offsets[i], highlights)}
      </p>
    )
  })
  return <div className="space-y-2 text-sm leading-relaxed text-slate-200">{nodes}</div>
}
