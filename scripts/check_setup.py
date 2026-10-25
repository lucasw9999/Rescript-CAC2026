#!/usr/bin/env python3
"""Check that this Mac can run Rescript, and say how to fix anything that is missing.

usage: python3 scripts/check_setup.py
Exit code 0 when everything needed is in place.
"""
import importlib, platform, re, shutil, subprocess, sys, urllib.request
from pathlib import Path

ok = True
def report(good, what, fix=""):
    global ok
    print(("  ✅ " if good else "  ❌ ") + what + ("" if good or not fix else f"\n     fix: {fix}"))
    ok &= good

print("Rescript setup check")
report(platform.system() == "Darwin" and platform.machine() == "arm64",
       f"M-series Mac ({platform.system()} {platform.machine()})",
       "Rescript needs an M-series Mac: the voice and transcription models run on MLX.")
report(sys.version_info >= (3, 10), f"Python {platform.python_version()}", "install Python 3.10 or newer (3.11 tested)")

ff = shutil.which("ffmpeg")
if ff:
    v = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout
    m = re.search(r"ffmpeg version n?(\d+)", v)
    major = int(m.group(1)) if m else 0
    report(major >= 7, f"ffmpeg {major or '?'} at {ff}", "brew upgrade ffmpeg  (version 7 or newer is required)")
else:
    report(False, "ffmpeg", "brew install ffmpeg")

missing = []
for mod, pkg in [("mlx_whisper", "mlx-whisper"), ("mlx_audio", "mlx-audio"), ("onnxruntime", "onnxruntime"),
                 ("transformers", "transformers"), ("huggingface_hub", "huggingface_hub"),
                 ("cv2", "opencv-python"), ("scipy", "scipy"), ("numpy", "numpy")]:
    try: importlib.import_module(mod)
    except Exception: missing.append(pkg)
here = Path(__file__).resolve().parent.parent
report(not missing, "Python packages" + (f" (missing: {', '.join(missing)})" if missing else ""),
       f"pip install -r {here / 'requirements.txt'}")

cx = shutil.which("codex")
if cx:
    li = subprocess.run([cx, "login", "status"], capture_output=True, text=True)
    report(li.returncode == 0, f"Codex CLI ({(li.stdout or li.stderr).strip() or 'not signed in'})",
           "codex login   (sign in with your ChatGPT account)")
else:
    report(False, "Codex CLI (the rescript command uses it to write the script)", "install the Codex CLI, then run: codex login")

try:
    urllib.request.urlopen(urllib.request.Request("https://huggingface.co", method="HEAD"), timeout=10)
    report(True, "huggingface.co reachable (models download on first run)")
except Exception as e:
    report(False, f"huggingface.co reachable ({type(e).__name__})",
           "allow huggingface.co through your proxy/sandbox, or pre-download the models on another network")

cache = Path.home() / ".cache" / "huggingface"
cache.mkdir(parents=True, exist_ok=True)
free = shutil.disk_usage(cache).free / 1e9
report(free >= 8, f"{free:.0f} GB free for model downloads", "free up about 8 GB of disk space")

print("\nReady to go." if ok else "\nFix the items marked ❌, then run this check again.")
sys.exit(0 if ok else 1)
