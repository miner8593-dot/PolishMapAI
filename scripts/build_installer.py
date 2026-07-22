"""Build a self-contained Windows installer around the tested portable app."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

stage = Path(os.environ["POLISHMAPAI_STAGE"])
artifacts = Path(os.environ["POLISHMAPAI_ARTIFACTS"])

with tempfile.TemporaryDirectory(prefix="polishmapai-installer-") as directory:
    work = Path(directory)
    payload = work / "payload"
    shutil.copytree(stage, payload)
    script = work / "installer.py"
    script.write_text(r'''
from pathlib import Path
import ctypes
import os
import shutil
import subprocess
import sys

target = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "PolishMapAI"
source = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "payload"
target.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, target, dirs_exist_ok=True)
desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop" / "PolishMapAI.cmd"
desktop.write_text(f'@start "" "{target / "PolishMapAI.exe"}"', encoding="utf-8")
ctypes.windll.user32.MessageBoxW(0, f"PolishMapAI installed to:\n{target}", "PolishMapAI", 0x40)
subprocess.Popen([str(target / "PolishMapAI.exe")])
''', encoding="utf-8")
    subprocess.run([
        os.sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", "PolishMapAI-Setup",
        "--distpath", str(artifacts), "--add-data", f"{payload};payload", str(script),
    ], cwd=work, check=True)

