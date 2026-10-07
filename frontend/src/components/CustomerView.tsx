import { PhoneOff, ShieldAlert, ShieldCheck } from 'lucide-react'
import type { AnalysisResponse } from '../types'
import { TIER_STYLE } from '../ui'

const COPY = {
  LOW: { en: 'This call looks normal.', hi: 'यह कॉल सामान्य लगती है।' },
  MEDIUM: { en: 'Be careful. Verify before you share anything or send money.', hi: 'सावधान रहें। कुछ भी बताने या पैसे भेजने से पहले verify करें।' },
  HIGH: { en: 'Stop! Do not send money or share codes. Verify the caller first.', hi: 'रुकिए! पैसे न भेजें और कोई कोड न बताएं। पहले caller को verify करें।' },
  CRITICAL: { en: 'Warning: this call is very likely a scam. End the call now.', hi: 'चेतावनी: यह कॉल बहुत संभव है कि फ्रॉड हो। अभी कॉल काट दें।' },
} as const

/** What a retail customer would see: a simple alert card, no scores or jargon. */
export function CustomerView({ a }: { a: AnalysisResponse }) {
  const s = TIER_STYLE[a.tier]
  const c = COPY[a.tier]
  const endCall = a.recommended_action.methods.includes('end_call_and_call_official_number')
  const Icon = a.tier === 'LOW' ? ShieldCheck : a.tier === 'CRITICAL' ? PhoneOff : ShieldAlert
  return (
    <div className="mx-auto w-64 rounded-[2rem] border-4 border-slate-700 bg-slate-950 p-3 shadow-xl">
      <div className="mx-auto mb-3 h-1.5 w-16 rounded-full bg-slate-700" />
      <div className={`rounded-2xl border p-4 ${s.border} ${s.bg}`}>
        <Icon className={`mb-2 h-8 w-8 ${s.text}`} />
        <p className="text-sm font-semibold text-slate-100">{c.en}</p>
        <p className="mt-1 text-sm text-slate-200">{c.hi}</p>
        {endCall && (
          <p className="mt-3 text-xs text-slate-300">
            Your bank will never ask for your OTP or PIN. Hang up and call the number on your card.
            <br />बैंक कभी OTP/PIN नहीं मांगता। कॉल काटकर अपने कार्ड पर दिए नंबर पर कॉल करें।
          </p>
        )}
        {a.tier !== 'LOW' && <p className="mt-3 text-xs text-slate-400">Report fraud: 1930 · cybercrime.gov.in</p>}
      </div>
      <p className="mt-2 text-center text-[10px] text-slate-600">Demo of the customer alert (synthetic)</p>
    </div>
  )
}
