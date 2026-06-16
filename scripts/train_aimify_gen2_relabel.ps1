param(
    [int]$Batch = 4,
    [int]$Workers = 2,
    [int]$ImgSize = 960,
    [int]$Epochs = 120,
    [double]$Lr0 = 0.002,
    [double]$Lrf = 0.01,
    [string]$BaseModel = "C:\AI\assaultcube.pt",
    [string]$Data = "C:\AI\dataset\aimify_relabel_20260611_corrected_split\data.yaml"
)

$ErrorActionPreference = "Stop"

Set-Location "C:\AI"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runName = "aimify_gen2_relabel_$stamp"
$runDir = "C:\AI\runs\detect\$runName"
$best = "$runDir\weights\best.pt"
$output = "C:\AI\assaultcube.pt"
$backup = "C:\AI\assaultcube_before_$runName.pt"
$logDir = "C:\AI\logs"
$log = "$logDir\$runName.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function LogLine([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $log -Value $line -Encoding utf8
}

if (-not (Test-Path -LiteralPath $Data)) {
    throw "Dataset yaml not found: $Data"
}
if (-not (Test-Path -LiteralPath $BaseModel)) {
    throw "Base model not found: $BaseModel"
}

Copy-Item -LiteralPath $BaseModel -Destination $backup -Force

LogLine "AImify GEN2 relabel training started"
LogLine "Run: $runDir"
LogLine "Data: $Data"
LogLine "Base: $BaseModel"
LogLine "Backup: $backup"
LogLine "Params: epochs=$Epochs imgsz=$ImgSize batch=$Batch workers=$Workers lr0=$Lr0 lrf=$Lrf"

& .\.venv\Scripts\python.exe -m scripts.train `
    --model $BaseModel `
    --data $Data `
    --epochs $Epochs `
    --imgsz $ImgSize `
    --batch $Batch `
    --device 0 `
    --name $runName `
    --patience $Epochs `
    --workers $Workers `
    --cos-lr `
    --close-mosaic 15 `
    --save-period 10 `
    --exist-ok `
    --lr0 $Lr0 `
    --lrf $Lrf 2>&1 | Tee-Object -FilePath $log -Append

$trainExit = $LASTEXITCODE
if ($trainExit -ne 0) {
    throw "Training failed with exit code $trainExit"
}

if (-not (Test-Path -LiteralPath $best)) {
    throw "Best model not found after training: $best"
}

LogLine "Training complete, selecting better model by EnemyHead validation metrics"

& .\.venv\Scripts\python.exe -m scripts.select_better_model `
    --baseline $backup `
    --candidate $best `
    --output $output `
    --data $Data `
    --class-name EnemyHead `
    --imgsz $ImgSize `
    --batch 1 `
    --device 0 2>&1 | Tee-Object -FilePath $log -Append

$selectExit = $LASTEXITCODE
if ($selectExit -ne 0) {
    throw "Model selection failed with exit code $selectExit"
}

& .\.venv\Scripts\python.exe -c "from ultralytics import YOLO; print(YOLO(r'C:\AI\assaultcube.pt').names)" 2>&1 |
    Tee-Object -FilePath $log -Append

LogLine "AImify GEN2 ready: $output"
LogLine "Run: $runDir"
LogLine "Backup: $backup"
