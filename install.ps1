$ErrorActionPreference = 'Stop'

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $rootDir

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    Write-Error 'Python 3 is required but was not found on PATH.'
    exit 1
}

$pythonExecutable = if ($pythonCmd.Name -eq 'py') { 'py -3' } else { 'python' }

if (-not (Test-Path '.venv')) {
    Write-Host 'Creating virtual environment...'
    if ($pythonExecutable -eq 'py -3') {
        & py -3 -m venv .venv
    } else {
        & python -m venv .venv
    }
}

$venvPython = Join-Path $rootDir '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Error 'The virtual environment was not created successfully.'
    exit 1
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

if (-not (Test-Path 'config.yaml')) {
    Copy-Item 'config.example.yaml' 'config.yaml'
}

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
}

if ($env:OBS_WEBSOCKET_PASSWORD) {
    $envLines = Get-Content '.env'
    $updated = $false
    for ($i = 0; $i -lt $envLines.Count; $i++) {
        if ($envLines[$i] -match '^OBS_WEBSOCKET_PASSWORD=') {
            $envLines[$i] = "OBS_WEBSOCKET_PASSWORD=$($env:OBS_WEBSOCKET_PASSWORD)"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $envLines += "OBS_WEBSOCKET_PASSWORD=$($env:OBS_WEBSOCKET_PASSWORD)"
    }
    Set-Content '.env' -Value $envLines
}

Write-Host ''
Write-Host 'PrintDirector installed successfully.'
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  .\.venv\Scripts\Activate.ps1'
Write-Host '  $env:OBS_WEBSOCKET_PASSWORD = "your-password"'
Write-Host '  python -m printdirector.main'
Write-Host ''
Write-Host 'If you want to run the demo instead:'
Write-Host '  python -m printdirector.main --demo'
