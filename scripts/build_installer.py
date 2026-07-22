"""Build a self-contained installer EXE without external proprietary tooling."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
stage = Path(os.environ["POLISHMAPAI_STAGE"])
artifacts = Path(os.environ["POLISHMAPAI_ARTIFACTS"])
work = Path(tempfile.mkdtemp(prefix="polishmapai-installer-"))
try:
    payload = work / "payload"
    shutil.copytree(stage, payload)
    script = work / "installer.py"
    script.write_text('''
from pathlib import Path
import ctypes, os, shutil, subprocess, sys

target=Path(os.environ.get("LOCALAPPDATA", Path.home()))/"Programs"/"PolishMapAI"
if target.exists(): shutil.rmtree(target)
source=Path(getattr(sys,"_MEIPASS",Path(__file__).parent))/"payload"
shutil.copytree(source,target)
desktop=Path(os.environ.get("USERPROFILE",Path.home()))/"Desktop"/"PolishMapAI.cmd"
desktop.write_text('@start "" "%s"\\PolishMapAI.exe' % target, encoding="utf-8")
ctypes.windll.user32.MessageBoxW(0, f"Installed to {target}", "PolishMapAI", 0x40)
subprocess.Popen([str(target/"PolishMapAI.exe")])
''', encoding="utf-8")
    subprocess.run([os.sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed", "--name", "PolishMapAI-Setup", "--distpath", str(artifacts), "--add-data", f"{payload};payload", str(script)], cwd=work, check=True)
finally:
    shutil.rmtree(work, ignore_errors=True)
