param(
    [int]$Batch = 4,
    [int]$Workers = 2,
    [int]$ImgSize = 960,
    [int]$Epochs = 120,
    [string]$BaseModel = "C:\AI\assaultcube.pt"
)

$ErrorActionPreference = "Stop"

Set-Location "C:\AI"

$data = "C:\AI\dataset\aimify_gen1_clean\data.yaml"
$runName = "aimify_gen1_clean"
$best = "C:\AI\runs\detect\$runName\weights\best.pt"
$output = "C:\AI\assaultcube.pt"

if (-not (Test-Path -LiteralPath $data)) {
    throw "Dataset yaml not found: $data"
}
if (-not (Test-Path -LiteralPath $BaseModel)) {
    throw "Base model not found: $BaseModel"
}

.\.venv\Scripts\python.exe -m scripts.train `
    --model $BaseModel `
    --data $data `
    --epochs $Epochs `
    --imgsz $ImgSize `
    --batch $Batch `
    --device 0 `
    --name $runName `
    --patience 45 `
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
Write-Host "AImify GEN1 clean updated: $output"
