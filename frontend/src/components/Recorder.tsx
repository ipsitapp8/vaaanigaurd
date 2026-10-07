import { useRef, useState } from 'react'
import { Mic, Square } from 'lucide-react'
import { btn } from '../ui'

/** Record from the microphone, then hand the clip over as a File (analysed like an upload). Hidden if unsupported. */
export function Recorder({ disabled, onRecorded }: { disabled: boolean; onRecorded: (f: File) => void }) {
  const [rec, setRec] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const mr = useRef<MediaRecorder | null>(null)

  if (typeof MediaRecorder === 'undefined' || !navigator.mediaDevices) return null

  const start = async () => {
    setMsg(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const chunks: Blob[] = []
      const r = new MediaRecorder(stream)
      r.ondataavailable = (e) => chunks.push(e.data)
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        const type = r.mimeType || 'audio/webm'
        onRecorded(new File(chunks, `recording.${type.includes('ogg') ? 'ogg' : 'webm'}`, { type }))
      }
      r.start()
      mr.current = r
      setRec(true)
    } catch {
      setMsg('Microphone unavailable or denied. Use a scenario or upload a file instead.')
    }
  }
  const stop = () => {
    mr.current?.stop()
    setRec(false)
  }

  return (
    <span className="inline-flex flex-col">
      {rec ? (
        <button onClick={stop} className={`${btn} border-red-500/60 text-red-200`}><Square className="h-4 w-4" /> Stop and analyse</button>
      ) : (
        <button onClick={start} disabled={disabled} className={btn}><Mic className="h-4 w-4" /> Record</button>
      )}
      {msg && <span className="mt-1 max-w-48 text-xs text-amber-300">{msg}</span>}
    </span>
  )
}
