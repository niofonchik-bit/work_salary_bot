$ErrorActionPreference = 'Stop'

py -3.12 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}

Write-Host 'Setup completed. Fill .env and run run.bat.' -ForegroundColor Green
