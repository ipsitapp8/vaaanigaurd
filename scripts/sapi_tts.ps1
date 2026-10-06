# Synthesizes each item of a JSON list [{"text": "...", "out": "path.wav"}] with a Windows SAPI voice.
# Used only to make PLACEHOLDER demo audio (see DECISIONS.md). Not a voice-cloning tool.
param([string]$JsonPath, [string]$Voice = "David")
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$match = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Name -like "*$Voice*" } | Select-Object -First 1
if ($match) { $synth.SelectVoice($match.VoiceInfo.Name) }
$synth.Rate = 0
$items = Get-Content -Raw -Encoding UTF8 $JsonPath | ConvertFrom-Json
foreach ($i in $items) {
  $synth.SetOutputToWaveFile($i.out)
  $synth.Speak($i.text)
  $synth.SetOutputToNull()
}
$synth.Dispose()
