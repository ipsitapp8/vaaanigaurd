# Primary Windows start command: backend (:8000) in a new window, frontend (:5173) here.
$root = $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\backend'; uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Set-Location "$root\frontend"
npm run dev