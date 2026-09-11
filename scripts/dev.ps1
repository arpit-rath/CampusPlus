<#
.SYNOPSIS
    Starts every piece of CampusPlus and does not return until each one has
    actually answered.

.DESCRIPTION
    The three-task VS Code chain starts the database, the API and the web app
    in separate terminals, which is fine until one of them fails: the web app
    still comes up on :3000, the browser still loads, and the only symptom is
    "Can't reach the API" inside the dashboard while the real error sits in a
    terminal tab nobody is looking at.

    This script fails loudly instead. It checks the prerequisites first, waits
    for the database to report healthy, waits for the API to answer /health,
    and waits for the web app to serve a page — printing a line per step and
    stopping at the first thing that is actually wrong, with what to do about
    it. The API and web processes each get their own window, so their logs are
    still there to read.

.PARAMETER Seed
    Also load the demo complaints once everything is up. Costs model quota,
    so it is off by default.

.PARAMETER ApiOnly
    Start the database and the API but not the web app.

.EXAMPLE
    .\scripts\dev.ps1
    .\scripts\dev.ps1 -Seed
#>

[CmdletBinding()]
param(
    [switch]$Seed,
    [switch]$ApiOnly
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$ApiDir = Join-Path $Root 'apps\api'
$WebDir = Join-Path $Root 'apps\web'
$Python = Join-Path $ApiDir '.venv\Scripts\python.exe'

# Runs a native executable and returns its exit code, swallowing its output.
#
# Windows PowerShell 5.1 turns anything a native command writes to stderr into
# an ErrorRecord, and with $ErrorActionPreference = 'Stop' that aborts the
# script even when the command succeeded — `docker compose` writes its normal
# progress there, so the whole thing died on a healthy database.
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments 2>&1 | Out-String | Out-Null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Write-Step($text) { Write-Host "[..] $text" -ForegroundColor Cyan }
function Write-Ok($text) { Write-Host "[ok] $text" -ForegroundColor Green }
function Write-Fail($text, $fix) {
    Write-Host "[!!] $text" -ForegroundColor Red
    if ($fix) { Write-Host "     $fix" -ForegroundColor Yellow }
}

# Returns $true when a GET against $url answers at all, whatever the status.
function Test-Url($url) {
    try {
        Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch [System.Net.WebException] {
        # A 4xx/5xx still means something is listening and answering.
        return $null -ne $_.Exception.Response
    } catch {
        return $false
    }
}

function Wait-ForUrl($url, $name, $seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (Test-Url $url) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

# Opens a command in its own window so its logs stay readable.
function Start-InWindow($title, $workingDir, $command) {
    $script = "`$host.UI.RawUI.WindowTitle = '$title'; Set-Location '$workingDir'; $command"
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoExit', '-Command', $script | Out-Null
}

Write-Host ''
Write-Host 'CampusPlus - starting the stack' -ForegroundColor White
Write-Host '-------------------------------'

# --- prerequisites ------------------------------------------------------

if (-not (Test-Path $Python)) {
    Write-Fail "No Python virtual environment at apps\api\.venv" `
        "Create it: cd apps\api; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path (Join-Path $ApiDir '.env'))) {
    Write-Fail "apps\api\.env is missing" `
        "Copy apps\api\.env.example to apps\api\.env and set GEMINI_API_KEY."
    exit 1
}

# --- 1. database --------------------------------------------------------

Write-Step 'Database (Postgres + pgvector on :5432)'
if ((Invoke-Native 'docker' @('info')) -ne 0) {
    Write-Fail 'Docker is not running' `
        "Start Docker Desktop and wait for it to say Running, then re-run this script. (No-Docker fallback: python scripts\dev_db.py)"
    exit 1
}

Push-Location $Root
try {
    $dbStarted = (Invoke-Native 'docker' @('compose', 'up', '-d', '--wait')) -eq 0
} finally {
    Pop-Location
}

if (-not $dbStarted) {
    Write-Fail 'The database container did not become healthy' `
        'Look at: docker compose logs db'
    exit 1
}
Write-Ok 'Database is healthy'

# --- 2. API -------------------------------------------------------------

Write-Step 'API (FastAPI on :8000)'
if (Test-Url 'http://localhost:8000/health') {
    Write-Ok 'API was already running'
} else {
    $inUse = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
    if ($inUse) {
        Write-Fail 'Port 8000 is taken by something that is not the API' `
            "Find it: Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess"
        exit 1
    }

    Start-InWindow 'CampusPlus API' $ApiDir ".\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

    if (-not (Wait-ForUrl 'http://localhost:8000/health' 'API' 45)) {
        Write-Fail 'The API did not answer within 45 seconds' `
            'Read the error in the "CampusPlus API" window that just opened - that is where the traceback is.'
        exit 1
    }
    Write-Ok 'API is answering on http://localhost:8000'
}

# --- 3. web -------------------------------------------------------------

if (-not $ApiOnly) {
    Write-Step 'Web (Next.js on :3000)'
    if (Test-Url 'http://localhost:3000') {
        Write-Ok 'Web app was already running'
    } else {
        Start-InWindow 'CampusPlus Web' $WebDir 'npm run dev'
        if (-not (Wait-ForUrl 'http://localhost:3000' 'web' 60)) {
            Write-Fail 'The web app did not answer within 60 seconds' `
                'Read the "CampusPlus Web" window.'
            exit 1
        }
        Write-Ok 'Web app is serving on http://localhost:3000'
    }
}

# --- 4. optional demo data ---------------------------------------------

if ($Seed) {
    Write-Step 'Seeding demo complaints (this calls the model - it takes a minute)'
    & $Python (Join-Path $Root 'scripts\seed_demo.py') --post
    if ($LASTEXITCODE -ne 0) {
        Write-Fail 'Seeding failed' 'The API is up, so the dashboard still works - just with no data.'
    } else {
        Write-Ok 'Demo complaints loaded'
    }
}

Write-Host ''
Write-Host 'Everything is up:' -ForegroundColor White
Write-Host '  Dashboard   http://localhost:3000/dashboard'
Write-Host '  Report form http://localhost:3000/report'
Write-Host '  API docs    http://localhost:8000/docs'
Write-Host ''
Write-Host 'Close the two CampusPlus windows to stop the API and the web app.'
Write-Host 'The database keeps running: docker compose stop'
Write-Host ''
