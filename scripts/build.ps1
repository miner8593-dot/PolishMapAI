$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ArtifactDir = Join-Path $ProjectRoot "artifacts"
$StageDir = Join-Path $ProjectRoot "build\portable"

Set-Location $ProjectRoot
$Python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $Python -m pip install --disable-pip-version-check -e ".[dev]"
& $Python -m pytest
& $Python -m PyInstaller --noconfirm --clean --windowed --name PolishMapAI --paths src --runtime-hook scripts/pyi_tk_runtime.py src/polishmapai/__main__.py

# A successful PyInstaller exit is insufficient: a broken Tcl/Tk bundle exits
# immediately before creating the editor window. Keep this smoke test in CI.
$BuiltExe = Join-Path $ProjectRoot "dist\PolishMapAI\PolishMapAI.exe"
$Smoke = Start-Process -FilePath $BuiltExe -PassThru
$Deadline = (Get-Date).AddSeconds(12)
do {
    Start-Sleep -Milliseconds 250
    $Smoke.Refresh()
} while (-not $Smoke.HasExited -and $Smoke.MainWindowTitle -notlike "PolishMapAI*" -and (Get-Date) -lt $Deadline)
if ($Smoke.HasExited -or $Smoke.MainWindowTitle -notlike "PolishMapAI*") {
    $Observed = if ($Smoke.HasExited) { "exit code $($Smoke.ExitCode)" } else { "window '$($Smoke.MainWindowTitle)'" }
    if (-not $Smoke.HasExited) { Stop-Process -Id $Smoke.Id -Force }
    $StartupLog = Join-Path (Split-Path -Parent $BuiltExe) "PolishMapAI-startup-error.log"
    if (Test-Path -LiteralPath $StartupLog) { Get-Content -LiteralPath $StartupLog }
    throw "Packaged PolishMapAI failed GUI smoke test: $Observed"
}
Stop-Process -Id $Smoke.Id -Force

if (Test-Path $StageDir) { Remove-Item -LiteralPath $StageDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $StageDir, $ArtifactDir | Out-Null
Copy-Item -Path (Join-Path $ProjectRoot "dist\PolishMapAI\*") -Destination $StageDir -Recurse
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $StageDir
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath (Join-Path $ArtifactDir "PolishMapAI-portable.zip") -Force

$env:POLISHMAPAI_STAGE = $StageDir
$env:POLISHMAPAI_ARTIFACTS = $ArtifactDir
& $Python scripts/build_installer.py
