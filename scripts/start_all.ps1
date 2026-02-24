# Set script location
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# Check venv
if (-not (Test-Path "venv")) {
    Write-Host "Error: Virtual environment (venv) not found! Please create it first."
    exit 1
}

# Ensure logs dir
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Force -Path "logs" | Out-Null
}

# Set PYTHONPATH
$env:PYTHONPATH = "$ProjectRoot;$env:PYTHONPATH"

# Start Watchlist Monitor Service
Write-Host "Starting Watchlist Monitor Service..."
$monitorProcess = Start-Process -FilePath "venv\Scripts\python.exe" -ArgumentList "-m src.monitor.watchlist_monitor" -RedirectStandardOutput "logs\monitor.out.log" -RedirectStandardError "logs\monitor.err.log" -PassThru -WindowStyle Hidden
Write-Host "Monitor Service started with PID: $($monitorProcess.Id)"

# Start Web Interface
Write-Host "Starting Web Interface..."
$webProcess = Start-Process -FilePath "venv\Scripts\python.exe" -ArgumentList "src\web\app.py" -RedirectStandardOutput "logs\web.out.log" -RedirectStandardError "logs\web.err.log" -PassThru -WindowStyle Hidden
Write-Host "Web Interface started with PID: $($webProcess.Id)"

# Save PIDs
$monitorProcess.Id | Out-File "logs\monitor.pid" -Encoding ascii
$webProcess.Id | Out-File "logs\web.pid" -Encoding ascii

Write-Host "All services started successfully!"
Write-Host "Web Interface available at: http://127.0.0.1:5001"
