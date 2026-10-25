#!/usr/bin/env python3
"""Rescript Studio: the drag-and-drop app for Rescript.

  rescript app                 (or: python3 app/server.py [--no-browser])

Starts a small web server on 127.0.0.1 only and opens it in the browser. Drop a recording, watch the four steps,
compare before and after, and fix any line by editing it or asking for a change. The work itself is done by the
same commands as the CLI (bin/rescript and scripts/), so the app and the command can never disagree.
Recordings are copied to ~/Movies/Rescript/ and the polished versions are written next to them.
"""
import importlib.machinery, importlib.util, json, os, re, subprocess, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
APP, SCRIPTS, CLI = ROOT / "app", ROOT / "scripts", ROOT / "bin" / "rescript"
LIB = Path(os.environ.get("RESCRIPT_LIB", Path.home() / "Movies" / "Rescript"))
PORT = int(os.environ.get("RESCRIPT_PORT", 8765))
TEMPLATES = SCRIPTS / "cursor_templates_macos_retina.npz"
VIDEO_EXT = {".mov", ".mp4", ".m4v"}

# Reuse the CLI's own helpers (work dir naming, script loading) instead of copying them.
_loader = importlib.machinery.SourceFileLoader("rescript_cli", str(CLI))
cli = importlib.util.module_from_spec(importlib.util.spec_from_loader("rescript_cli", _loader))
_loader.exec_module(cli)
VOICES = cli.VOICES

# The CLI runs ffmpeg and codex; when the app is opened from the Dock, PATH lacks Homebrew.
ENV = dict(os.environ, PYTHONUNBUFFERED="1")
ENV["PATH"] = ":".join(dict.fromkeys(["/opt/homebrew/bin", "/usr/local/bin", *ENV.get("PATH", "").split(":")]))


# ---------- projects ----------

def video_path(name):
    """The recording called `name` in the library, refusing anything that isn't a plain file name there."""
    if not name or "/" in name or name.startswith("."): raise ValueError("bad name")
    p = LIB / name
    if p.suffix.lower() not in VIDEO_EXT or not p.is_file(): raise FileNotFoundError(name)
    return p

def outputs(v):
    return v.with_name(f"{v.stem} - polished.mp4"), v.with_name(f"{v.stem} - polished (clean cursor).mp4")

def duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                        "-of", "json", str(p)], capture_output=True, text=True, env=ENV)
    try: return float(json.loads(r.stdout)["streams"][0]["duration"])
    except (ValueError, KeyError, IndexError): return None

def projects():
    if not LIB.exists(): return []
    vids = [p for p in LIB.iterdir() if p.suffix.lower() in VIDEO_EXT and " - polished" not in p.stem]
    out = []
    for v in sorted(vids, key=lambda p: p.stat().st_mtime, reverse=True):
        pol, _ = outputs(v)
        out.append({"name": v.name, "polished": pol.exists(), "modified": v.stat().st_mtime})
    return out

def stats(v, wd):
    """Real numbers for this recording: length, words and long pauses before and after."""
    W, S = cli.load(wd / "words.json"), cli.load(wd / "script.json")
    segs = cli.load(wd / "segs.json") if (wd / "segs.json").exists() else []
    gaps = [W[k][0] - W[k - 1][1] for k in range(1, len(W))]
    long_gaps = [g for g in gaps if g > 1.0]
    verify = cli.load(wd / "tts" / "verify.json") if (wd / "tts" / "verify.json").exists() else []
    pol, _ = outputs(v)
    return {"before_s": duration(v), "after_s": (duration(pol) if pol.exists() else None) or sum(s[3] for s in segs) or None,
            "words_before": len(W), "words_after": sum(len(cli.unit_text(u).split()) for u in S),
            "long_pauses": len(long_gaps), "long_pause_s": round(sum(long_gaps), 1),
            "lines": len(S), "suspects": sum(1 for c in verify if c["ratio"] < 0.9)}

def project(name):
    v = video_path(name)
    wd, (pol, clean) = cli.workdir(v), outputs(v)
    info = {"name": name, "polished": pol.exists(), "clean": clean.exists(), "workdir": str(wd), "lines": [], "stats": None}
    if pol.exists() and (wd / "segs.json").exists() and (wd / "script.json").exists():
        W, S = cli.load(wd / "words.json"), cli.load(wd / "script.json")
        verify = {c["unit"]: c for c in cli.load(wd / "tts" / "verify.json")} if (wd / "tts" / "verify.json").exists() else {}
        for i, ((t0, d), u) in enumerate(zip(cli.out_times(wd), S)):
            w = u if isinstance(u, list) else u.get("words")
            said = " ".join(x[2].strip() for x in W[w[0]:w[1] + 1]) if w else ""
            info["lines"].append({"i": i, "text": cli.unit_text(u), "said": said, "start": round(t0, 2), "dur": round(d, 2),
                                  "suspect": i in verify and verify[i]["ratio"] < 0.9})
        info["stats"] = stats(v, wd)
    return info


# ---------- one background job at a time ----------

JOB = {"busy": False, "name": None, "kind": None, "stage": 0, "stages": 6, "detail": "", "log": [], "error": None,
       "started": 0.0, "finished": 0.0, "line": None}
LOCK = threading.Lock()

# What each CLI stage is called in the app: plain words, no model names.
STAGE_TEXT = {1: "Writing down every word", 2: "Writing a clean script with GPT", 3: "Getting your voice ready",
              4: "Speaking every line in your voice", 5: "Re-cutting the video to fit", 6: "Checking the sound and the slides",
              7: "Removing the mouse cursor"}

def track(line):
    """Turn the CLI's progress lines into stage numbers and a short status for the app."""
    line = line.split("\r")[-1].rstrip()
    if not line or line.startswith(("Fetching", "[transformers]")): return
    JOB["log"] = (JOB["log"] + [line])[-300:]
    if m := re.match(r"== (\d+)/(\d+) (.*)", line):
        JOB["stage"], JOB["stages"] = int(m[1]), max(JOB["stages"], int(m[2]))
        JOB["detail"] = STAGE_TEXT.get(JOB["stage"], m[3])
    elif m := re.match(r"u(\d\d)\s+([\d.]+)s$", line.strip()):
        JOB["detail"] = f"Spoke line {int(m[1]) + 1}"
    elif m := re.match(r"duration ([\d.]+)s, (\d+) words", line):
        JOB["detail"] = f"Heard {m[2]} words in {float(m[1]):.0f} s"
    elif m := re.match(r"\s*u(\d\d) reworded: (.*)", line):
        JOB["detail"] = f"Reworded line {int(m[1]) + 1}"
    elif re.match(r"\d+ frames|group \d+/", line):
        JOB["detail"] = "Finding and erasing the cursor"

def run_job(steps):
    """Run (label, command, cwd) steps in order. A label is shown as its own stage before its command runs."""
    try:
        for label, cmd, cwd in steps:
            if label: track(label)
            p = subprocess.Popen(cmd, cwd=cwd, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for out in p.stdout: track(out)
            if p.wait():
                tail = [l for l in JOB["log"] if l.strip()][-6:]
                raise RuntimeError("\n".join(tail) or f"exit code {p.returncode}")
        JOB["detail"] = "Done"
    except Exception as e:
        JOB["error"] = str(e)
    finally:
        JOB["busy"], JOB["finished"] = False, time.time()

def start(name, kind, steps, line=None):
    with LOCK:
        if JOB["busy"]: raise RuntimeError(f"Rescript is still working on {JOB['name']}.")
        JOB.update(busy=True, name=name, kind=kind, stage=0, stages=6, detail="Starting", log=[], error=None,
                   started=time.time(), finished=0.0, line=line)
    threading.Thread(target=run_job, args=(steps,), daemon=True).start()

def cursor_steps(v):
    pol, clean = outputs(v)
    wd = cli.workdir(v)
    py = sys.executable
    return [("== 7/7 Remove the mouse cursor", [py, str(SCRIPTS / "cursor_detect.py"), str(pol), str(TEMPLATES), str(wd / "det.json")], str(wd)),
            (None, [py, str(SCRIPTS / "cursor_erase.py"), str(pol), str(TEMPLATES), str(wd / "det.json"), str(clean)], str(wd))]

def polish(name, voice="", cursor=False, rewrite=False, fresh=False):
    v = video_path(name)
    cmd = [sys.executable, str(CLI), "polish", str(v)]
    if voice: cmd += ["--voice", voice]
    if rewrite: cmd += ["--rewrite"]
    if fresh: cmd += ["--fresh"]
    start(name, "polish", [(None, cmd, None)] + (cursor_steps(v) if cursor else []))

def fix_line(name, i, text=None, change=None):
    """Re-speak one line: with new text typed by the user, or with a change described in words (GPT rewrites it)."""
    v = video_path(name)
    wd = cli.workdir(v)
    S, st = cli.load(wd / "script.json"), cli.out_times(wd)
    if not 0 <= i < len(S): raise ValueError("no such line")
    if text is not None:
        text = " ".join(text.split())
        if not text: raise ValueError("the line is empty")
        if isinstance(S[i], dict): S[i]["text"] = text
        else: S[i][2] = text
        cli.save(wd / "script.json", S)
    at = f"{st[i][0] + min(0.05, st[i][1] / 2):.2f}"
    cmd = [sys.executable, str(CLI), "fix", str(v), at] + ([change] if change else [])
    start(name, "fix", [(None, cmd, None)], line=i)


# ---------- HTTP ----------

ASSET_TYPES = {".js": "application/javascript", ".mjs": "application/javascript", ".css": "text/css", ".png": "image/png",
               ".svg": "image/svg+xml", ".ttf": "font/ttf", ".woff2": "font/woff2", ".txt": "text/plain"}
STATIC = {"/": ("index.html", "text/html"), "/studio.css": ("studio.css", "text/css"),
          "/studio.js": ("studio.js", "application/javascript")}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body=b"", ctype="application/json", headers=()):
        if isinstance(body, (dict, list)): body = json.dumps(body).encode()
        elif isinstance(body, str): body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, val in headers: self.send_header(k, val)
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in STATIC:
                f, ctype = STATIC[u.path]
                return self.send(200, (APP / f).read_bytes(), ctype + "; charset=utf-8")
            if u.path.startswith("/assets/"): return self.asset(unquote(u.path[1:]))
            if u.path == "/api/ping": return self.send(200, {"app": "rescript"})
            if u.path == "/api/projects": return self.send(200, projects())
            if u.path == "/api/project": return self.send(200, project(q["name"]))
            if u.path == "/api/job":
                total = None
                try: total = len(cli.load(cli.workdir(video_path(JOB["name"])) / "script.json"))
                except Exception: pass
                return self.send(200, {**JOB, "total": total,
                                       "elapsed": round((JOB["finished"] or time.time()) - JOB["started"], 1) if JOB["started"] else 0})
            if u.path == "/api/voices":
                return self.send(200, sorted(p.name[:-8] for p in VOICES.glob("*_ref.wav")) if VOICES.exists() else [])
            if u.path == "/media": return self.media(q["name"], q.get("which", "original"))
            self.send(404, {"error": "not found"})
        except (KeyError, ValueError, FileNotFoundError) as e:
            self.send(404, {"error": f"not found: {e}"})

    do_HEAD = do_GET

    def do_POST(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/upload": return self.upload()
            b = self.body()
            if u.path == "/api/polish":
                polish(b["name"], b.get("voice", ""), bool(b.get("cursor")), bool(b.get("rewrite")), bool(b.get("fresh")))
            elif u.path == "/api/line":
                fix_line(b["name"], int(b["i"]), b.get("text"), b.get("change"))
            elif u.path == "/api/cursor":
                start(b["name"], "cursor", cursor_steps(video_path(b["name"])))
            elif u.path == "/api/save-voice":
                v = video_path(b["name"]); wd = cli.workdir(v)
                voice = re.sub(r"[^A-Za-z0-9_-]+", "-", b["voice"]).strip("-")
                if not voice: raise ValueError("give the voice a name")
                VOICES.mkdir(exist_ok=True)
                for ext in ("wav", "txt"): (VOICES / f"{voice}_ref.{ext}").write_bytes((wd / f"ref.{ext}").read_bytes())
            elif u.path == "/api/reveal":
                v = video_path(b["name"]); pol, clean = outputs(v)
                subprocess.run(["open", "-R", str(clean if clean.exists() else pol if pol.exists() else v)])
            else:
                return self.send(404, {"error": "not found"})
            self.send(200, {"ok": True})
        except RuntimeError as e:
            self.send(409, {"error": str(e)})
        except (KeyError, ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            self.send(400, {"error": str(e)})

    def asset(self, rel):
        """Files under app/assets/ (characters, fonts, three.js), and nothing outside that folder."""
        root = (APP / "assets").resolve()
        p = (APP / rel).resolve()
        if root not in p.parents or not p.is_file(): return self.send(404, {"error": "not found"})
        ctype = ASSET_TYPES.get(p.suffix.lower(), "application/octet-stream")
        self.send(200, p.read_bytes(), ctype)

    def upload(self):
        """Copy a dropped recording into the library. The browser can't hand over a file path, only the bytes."""
        name = Path(unquote(self.headers.get("X-Filename", ""))).name
        if Path(name).suffix.lower() not in VIDEO_EXT: return self.send(400, {"error": "Drop a .mov or .mp4 screen recording."})
        n = int(self.headers.get("Content-Length") or 0)
        LIB.mkdir(parents=True, exist_ok=True)
        dest = LIB / name
        if dest.exists() and dest.stat().st_size == n:      # the same recording again: keep its finished work
            self.rfile.read(n); return self.send(200, {"name": dest.name})
        k = 2
        while dest.exists(): dest = LIB / f"{Path(name).stem} {k}{Path(name).suffix}"; k += 1
        tmp = dest.with_name(dest.name + ".part")
        with open(tmp, "wb") as f:
            left = n
            while left:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk: break
                f.write(chunk); left -= len(chunk)
        if left: tmp.unlink(missing_ok=True); return self.send(400, {"error": "upload interrupted"})
        tmp.rename(dest)
        self.send(200, {"name": dest.name})

    def media(self, name, which):
        """Serve a video with HTTP range support, which <video> needs for seeking (Safari won't play without it)."""
        v = video_path(name); pol, clean = outputs(v)
        p = {"original": v, "polished": pol, "clean": clean}[which]
        if not p.exists(): return self.send(404, {"error": "not made yet"})
        size = p.stat().st_size
        ctype = "video/quicktime" if p.suffix.lower() == ".mov" else "video/mp4"
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        a, b = 0, size - 1
        if m and (m[1] or m[2]):
            if m[1]: a, b = int(m[1]), int(m[2]) if m[2] else size - 1
            else: a = size - int(m[2])
            b = min(b, size - 1)
        self.send_response(206 if m else 200)
        self.send_header("Content-Type", ctype); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(b - a + 1)); self.send_header("Cache-Control", "no-store")
        if m: self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.end_headers()
        if self.command == "HEAD": return
        with open(p, "rb") as f:
            f.seek(a); left = b - a + 1
            try:
                while left:
                    chunk = f.read(min(left, 1 << 20))
                    if not chunk: break
                    self.wfile.write(chunk); left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError): pass   # the player seeked elsewhere


def main():
    # Try PORT, then the next ports: another program may already be using it (the app used to quit silently then).
    for port in range(PORT, PORT + 20):
        url = f"http://127.0.0.1:{port}/"
        try:                                # already running (opened twice from the Dock): just show it
            if json.load(urlopen(url + "api/ping", timeout=1)).get("app") == "rescript":
                if "--no-browser" not in sys.argv: webbrowser.open(url)
                return
        except Exception:
            pass
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:                     # taken by something else: try the next one
            continue
    else:
        sys.exit(f"Rescript Studio: ports {PORT}-{PORT + 19} are all in use.")
    print(f"Rescript Studio is running at {url}  (Ctrl-C to stop)", flush=True)
    if "--no-browser" not in sys.argv: threading.Timer(0.6, webbrowser.open, [url]).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
