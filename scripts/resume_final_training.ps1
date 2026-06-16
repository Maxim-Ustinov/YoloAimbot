param(
    [int]$Batch = 4,
    [int]$Workers = 2,
    [int]$ImgSize = 960,
    [int]$Epochs = 120
)

$ErrorActionPreference = "Stop"

Set-Location "C:\AI"

$runName = "assaultcube_final_unified_gpu"
$fallbackCheckpoint = "C:\AI\runs\detect\assaultcube_final_unified\weights\last.pt"
$runCheckpoint = "C:\AI\runs\detect\$runName\weights\last.pt"
$checkpoint = if (Test-Path -LiteralPath $runCheckpoint) { $runCheckpoint } else { $fallbackCheckpoint }
$best = "C:\AI\runs\detect\$runName\weights\best.pt"
$output = "C:\AI\assaultcube.pt"

if (-not (Test-Path -LiteralPath $checkpoint)) {
    throw "Checkpoint not found: $checkpoint"
}

# Do not use Ultralytics resume=True here. On Windows it restores the old
# cache/workers/batch settings and can stall before CUDA training starts.
# This continues from last.pt weights, but starts a fresh, GPU-friendlier run.
.\.venv\Scripts\python.exe -m scripts.train `
    --model $checkpoint `
    --data "C:\AI\dataset\assaultcube_unified_3cls_final\data.yaml" `
    --epochs $Epochs `
    --imgsz $ImgSize `
    --batch $Batch `
    --device 0 `
    --name $runName `
    --patience 35 `
    --workers $Workers `
    --cos-lr `
    --close-mosaic 15 `
    --save-period 10 `
    --exist-ok

if ($LASTEXITCODE -ne 0) {
    throw "Training failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $best)) {
    throw "Best model not found after training: $best"
}

Copy-Item -LiteralPath $best -Destination $output -Force
.\.venv\Scripts\python.exe -c "from ultralytics import YOLO; print(YOLO(r'C:\AI\assaultcube.pt').names)"
Write-Host "AImify GEN1 updated: $output"
