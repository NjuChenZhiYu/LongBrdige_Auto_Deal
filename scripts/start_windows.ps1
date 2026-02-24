$env:PYTHONPATH = "$PSScriptRoot\.."
$python = "$PSScriptRoot\..\venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Error: Python executable not found at $python" -ForegroundColor Red
    exit 1
}

# Start Monitor
Write-Host "Starting Monitor Service..." -ForegroundColor Cyan
Start-Process -FilePath $python -ArgumentList "-m src.monitor.watchlist_monitor" -WorkingDirectory "$PSScriptRoot\.." -WindowStyle Minimized

# Start Web
Write-Host "Starting Web Interface..." -ForegroundColor Cyan
Start-Process -FilePath $python -ArgumentList "src\web\app.py" -WorkingDirectory "$PSScriptRoot\.."

Write-Host "Services started. Web Interface should be available at http://localhost:5001" -ForegroundColor Green
