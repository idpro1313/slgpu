# Typecheck frontend (tsc) — вызывайте из корня репозитория: .\web\verify-frontend.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot/frontend
npm run typecheck
