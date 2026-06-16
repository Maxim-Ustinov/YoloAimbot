# setup.ps1 - create .venv and install dependencies.
#
# A virtual environment is NOT portable between machines (it hardcodes the
# Python path and stores compiled packages built for one Python version).
# So DON'T copy the .venv folder around - run this script on each machine.
#
# Requires a real Python from python.org on PATH. Check first:
#   python --version
#
# Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File setup.ps1

if (Test-Path .venv) {
    Write-Host "Removing old .venv..."
    Remove-Item -Recurse -Force .venv
}
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
Write-Host ""
Write-Host "Done. Run with:  .venv\Scripts\python -m src.gui.app   (or run.ps1)"
