param(
    [int]$Batch = 4,
    [int]$Workers = 2,
    [int]$ImgSize = 960,
    [int]$Epochs = 60,
    [double]$Lr0 = 0.002,
    [double]$Lrf = 0.01,
    [string]$BaseModel = "C:\AI\assaultcube.pt"
)

$ErrorActionPreference = "Stop"

Set-Location "C:\AI"

$data = "C:\AI\dataset\aimify_gen1_clean\data.yaml"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runName = "aimify_gen1_finetune_$stamp"
$runDir = "C:\AI\runs\detect\$runName"
$best = "$runDir\weights\best.pt"
$output = "C:\AI\assaultcube.pt"
$backup = "C:\AI\assaultcube_before_$runName.pt"

if (-not (Test-Path -LiteralPath $data)) {
    throw "Dataset yaml not found: $data"
}
if (-not (Test-Path -LiteralPath $BaseModel)) {
    throw "Base model not found: $BaseModel"
}

Copy-Item -LiteralPath $BaseModel -Destination $backup -Force

.\.venv\Scripts\python.exe -m scripts.train `
    --model $BaseModel `
    --data $data `
    --epochs $Epochs `
    --imgsz $ImgSize `
    --batch $Batch `
    --device 0 `
    --name $runName `
    --patience 25 `
    --workers $Workers `
    --cos-lr `
    --close-mosaic 10 `
    --save-period 10 `
    --exist-ok `
    --lr0 $Lr0 `
    --lrf $Lrf

if ($LASTEXITCODE -ne 0) {
    throw "Training failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $best)) {
    throw "Best model not found after training: $best"
}

.\.venv\Scripts\python.exe -m scripts.select_better_model `
    --baseline $backup `
    --candidate $best `
    --output $output `
    --data $data `
    --class-name EnemyHead `
    --imgsz $ImgSize `
    --batch 1 `
    --device 0

.\.venv\Scripts\python.exe -c "from ultralytics import YOLO; print(YOLO(r'C:\AI\assaultcube.pt').names)"
Write-Host "AImify GEN1 fine-tuned: $output"
Write-Host "Run: $runDir"
Write-Host "Backup: $backup"
