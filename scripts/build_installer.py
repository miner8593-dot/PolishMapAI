"""Build a native Microsoft IExpress installer around the portable ZIP."""
from pathlib import Path
import os
import subprocess
import tempfile
import time

stage = Path(os.environ["POLISHMAPAI_STAGE"])
artifacts = Path(os.environ["POLISHMAPAI_ARTIFACTS"])
portable = artifacts / "PolishMapAI-portable.zip"
output = artifacts / "PolishMapAI-Setup.exe"

with tempfile.TemporaryDirectory(prefix="polishmapai-iexpress-") as directory:
    work = Path(directory)
    installer = work / "install_polishmapai.ps1"
    installer.write_text(r'''
$ErrorActionPreference = "Stop"
$Target = Join-Path $env:LOCALAPPDATA "Programs\PolishMapAI"
$Payload = Join-Path $PSScriptRoot "PolishMapAI-portable.zip"
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Expand-Archive -LiteralPath $Payload -DestinationPath $Target -Force
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "PolishMapAI.lnk"))
$Shortcut.TargetPath = Join-Path $Target "PolishMapAI.exe"
$Shortcut.WorkingDirectory = $Target
$Shortcut.Save()
Start-Process -FilePath (Join-Path $Target "PolishMapAI.exe")
''', encoding="utf-8-sig")
    sed = work / "setup.sed"
    sed.write_text(f'''[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles
[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=PolishMapAI installed.
TargetName={output}
FriendlyName=PolishMapAI Setup
AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\install_polishmapai.ps1
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
FILE0="install_polishmapai.ps1"
FILE1="PolishMapAI-portable.zip"
[SourceFiles]
SourceFiles0={work}\\
SourceFiles1={artifacts}\\
[SourceFiles0]
%FILE0%=
[SourceFiles1]
%FILE1%=
''', encoding="utf-8-sig")
    subprocess.run(["iexpress.exe", "/N", "/Q", str(sed)], check=True)
    for _ in range(120):
        if output.exists():
            break
        time.sleep(.25)
    if not output.exists():
        raise RuntimeError("IExpress did not produce the installer")
