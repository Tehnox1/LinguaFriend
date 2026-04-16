$ErrorActionPreference = 'Stop'
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path $py)) {
  Write-Host 'Не найден .venv\Scripts\python.exe'
  exit 1
}
& $py web_app.py
