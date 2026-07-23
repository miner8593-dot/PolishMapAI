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
$Smoke = Start-Process -FilePath $BuiltExe -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 4
if ($Smoke.HasExited) {
    throw "Packaged PolishMapAI exited during GUI smoke test (exit code $($Smoke.ExitCode))"
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
