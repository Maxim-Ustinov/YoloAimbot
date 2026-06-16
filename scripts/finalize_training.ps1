param(
    [Parameter(Mandatory = $true)]
    [int]$TrainPid,

    [Parameter(Mandatory = $true)]
    [string]$RunDir,

    [Parameter(Mandatory = $true)]
    [string]$OutputModel,

    [Parameter(Mandatory = $true)]
    [string]$LogPath
)

$ErrorActionPreference = "Continue"

function Write-Status($Message) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$stamp $Message" | Out-File -FilePath $LogPath -Append -Encoding utf8
}

Write-Status "waiting for train pid $TrainPid"
try {
    Wait-Process -Id $TrainPid
} catch {
    Write-Status "wait failed: $($_.Exception.Message)"
}

Start-Sleep -Seconds 5
$best = Join-Path $RunDir "weights\best.pt"
if (Test-Path -LiteralPath $best) {
    Copy-Item -LiteralPath $best -Destination $OutputModel -Force
    Write-Status "AImify GEN1 updated: $best -> $OutputModel"
    try {
        & "C:\AI\.venv\Scripts\python.exe" -c "from ultralytics import YOLO; print(YOLO(r'C:\AI\assaultcube.pt').names)" 2>&1 |
            Out-File -FilePath $LogPath -Append -Encoding utf8
    } catch {
        Write-Status "model check failed: $($_.Exception.Message)"
    }
} else {
    Write-Status "best model not found: $best"
}
