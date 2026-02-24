# Set script location
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# Function to stop process by PID file or search
function Stop-ServiceProcess {
    param (
        [string]$PidFile,
        [string]$SearchPattern,
        [string]$ServiceName
    )

    if (Test-Path $PidFile) {
        $ProcessId = Get-Content $PidFile
        Write-Host "Stopping $ServiceName (PID: $ProcessId)..."
        try {
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
            Remove-Item $PidFile -Force
            Write-Host "$ServiceName stopped."
        } catch {
            Write-Host "Warning: Failed to stop $ServiceName with PID $ProcessId. Process might not be running."
            Remove-Item $PidFile -Force
        }
    } else {
        Write-Host "$ServiceName PID file not found. Checking running processes..."
        # Note: CommandLine check requires WMI/CIM
        $Processes = Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*$SearchPattern*" }
        if ($Processes) {
            foreach ($proc in $Processes) {
                Write-Host "Found running $ServiceName process: $($proc.ProcessId). Killing..."
                Stop-Process -Id $proc.ProcessId -Force
            }
        } else {
            Write-Host "No running $ServiceName process found."
        }
    }
}

# Stop Monitor Service
Stop-ServiceProcess -PidFile "logs\monitor.pid" -SearchPattern "src.monitor.watchlist_monitor" -ServiceName "Monitor Service"

# Stop Web Interface
Stop-ServiceProcess -PidFile "logs\web.pid" -SearchPattern "src\web\app.py" -ServiceName "Web Interface"

Write-Host "All services stopped."
