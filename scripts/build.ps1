$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ArtifactDir = Join-Path $ProjectRoot "artifacts"
$StageDir = Join-Path $ProjectRoot "build\portable"

Set-Location $ProjectRoot
$Python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $Python -m pip install --disable-pip-version-check -e ".[dev]"
& $Python -m pytest
& $Python -m PyInstaller --noconfirm --clean --windowed --name PolishMapAI --paths src --runtime-hook scripts/pyi_tk_runtime.py src/polishmapai/__main__.py

# A successful PyInstaller exit is insufficient. Open and progressively render
# a large map while a heartbeat measures responsiveness of the Tk event loop.
$BuiltExe = Join-Path $ProjectRoot "dist\PolishMapAI\PolishMapAI.exe"
$SmokeMap = Join-Path $ProjectRoot "build\gui-smoke.mp"
$SmokeReport = Join-Path $ProjectRoot "build\gui-smoke.json"
& $Python scripts/generate_smoke_map.py $SmokeMap
$env:POLISHMAPAI_SMOKE_REPORT = $SmokeReport
$Smoke = Start-Process -FilePath $BuiltExe -ArgumentList @("--smoke-test", $SmokeMap) -PassThru
$Deadline = (Get-Date).AddSeconds(55)
do {
    Start-Sleep -Milliseconds 250
    $Smoke.Refresh()
} while (-not $Smoke.HasExited -and (Get-Date) -lt $Deadline)
if (-not $Smoke.HasExited) {
    Stop-Process -Id $Smoke.Id -Force
    $Observed = "timeout"
    $StartupLog = Join-Path (Split-Path -Parent $BuiltExe) "PolishMapAI-startup-error.log"
    if (Test-Path -LiteralPath $StartupLog) { Get-Content -LiteralPath $StartupLog }
    throw "Packaged PolishMapAI failed GUI smoke test: $Observed"
}
if ($Smoke.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $SmokeReport)) {
    throw "Packaged PolishMapAI GUI smoke test exited with code $($Smoke.ExitCode) without a valid report"
}
$SmokeResult = Get-Content -LiteralPath $SmokeReport -Raw | ConvertFrom-Json
if (-not $SmokeResult.ok -or $SmokeResult.objects -lt 18000 -or $SmokeResult.max_heartbeat_gap_ms -gt 750) {
    $SmokeResult | ConvertTo-Json -Depth 5
    throw "Packaged PolishMapAI GUI smoke test reported an unresponsive or incomplete run"
}
$SmokeResult | ConvertTo-Json -Depth 5

if (Test-Path $StageDir) { Remove-Item -LiteralPath $StageDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $StageDir, $ArtifactDir | Out-Null
Copy-Item -LiteralPath $SmokeReport -Destination (Join-Path $ArtifactDir "GUI-smoke.json")
Copy-Item -Path (Join-Path $ProjectRoot "dist\PolishMapAI\*") -Destination $StageDir -Recurse
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $StageDir
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath (Join-Path $ArtifactDir "PolishMapAI-portable.zip") -Force

$env:POLISHMAPAI_STAGE = $StageDir
$env:POLISHMAPAI_ARTIFACTS = $ArtifactDir
& $Python scripts/build_installer.py
