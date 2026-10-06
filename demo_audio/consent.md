# demo_audio / consent

**Current files are PLACEHOLDERS.** They were generated with Windows SAPI text-to-speech
(`scripts/make_placeholder_audio.py`, voices "Microsoft David/Zira Desktop", English-US) reading
romanized Hinglish, then band-limited and noised to mimic telephony. They contain **no real person's
voice and no voice cloning**, so no consent is needed for them.

Because an English voice reads Hinglish, real ASR transcribes them imperfectly; scenarios fall back to the
sidecar transcript in the scenario JSON when ASR is unavailable (labelled "fallback transcript").

## To replace with real recordings (SPEC section M)
| Scenario | Needs | Consent from |
|---|---|---|
| s1, s6 (genuine) | Team-member recording | _name, date, scope_ |
| s2-s5 (cloned) | XTTS-v2 / Piper clone of a consenting team member | _name, date, scope_ |

Keep the same filenames, update `start`/`end` of each segment in the scenario JSON, and record each
consenting person here.
